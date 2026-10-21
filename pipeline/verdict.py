"""Per-plot verdicts with evidence anyone can recompute.

A plot's verdict is computed on its own window: the plot's bounding box plus 200 m, snapped to the Sentinel-2
20 m grid. The evidence file lists the exact scenes, the rule and the numbers. Its keccak-256 hash goes on-chain,
so a recheck that reads the same scenes must land on the same figure, and anyone who gets a different one can
challenge.
"""
import json

import numpy as np
from Crypto.Hash import keccak
from pyproj import Transformer
from rasterio.features import rasterize
from shapely.geometry import mapping, shape
from shapely.ops import transform as shp_transform

import burnscar as bs

CRS = "EPSG:32643"  # UTM 43N, the Sentinel-2 grid over Punjab
MARGIN = 200  # metres around the plot, so the 3x3 smoothing and patch test see the plot's neighbourhood
CELL = 50  # metres: land cells for the on-chain "enrolled once" check


def keccak256(data: bytes) -> str:
    return "0x" + keccak.new(digest_bits=256, data=data).hexdigest()


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def polygon_hash(geom_lonlat) -> str:
    g = {"type": "Polygon", "coordinates": [[[round(x, 6), round(y, 6)] for x, y in ring] for ring in mapping(shape(geom_lonlat))["coordinates"]]}
    return keccak256(canonical(g))


def to_utm(geom_lonlat):
    tr = Transformer.from_crs("EPSG:4326", CRS, always_xy=True)
    return shp_transform(lambda x, y, z=None: tr.transform(x, y), shape(geom_lonlat))


def window(poly_utm, res=20):
    l, b, r, t = poly_utm.bounds
    l, b = np.floor((l - MARGIN) / res) * res, np.floor((b - MARGIN) / res) * res
    r, t = np.ceil((r + MARGIN) / res) * res, np.ceil((t + MARGIN) / res) * res
    return {"crs": CRS, "transform": (res, 0.0, l, 0.0, -res, t), "shape": (int((t - b) / res), int((r - l) / res)), "bounds": (l, b, r, t)}


def cells(poly_utm):
    """50 m grid squares whose centre lies inside the plot. Neighbouring plots that don't overlap never share one."""
    from shapely.geometry import Point

    l, b, r, t = poly_utm.bounds
    out = []
    for gx in range(int(l // CELL), int(r // CELL) + 1):
        for gy in range(int(b // CELL), int(t // CELL) + 1):
            if poly_utm.contains(Point(gx * CELL + CELL / 2, gy * CELL + CELL / 2)):
                out.append((43 << 48) | (gx << 24) | gy)
    return out


def crop(arrays, big, win):
    """Cut a plot window out of a study-area array set (both on the same 20 m grid)."""
    c0 = int(round((win["bounds"][0] - big["bounds"][0]) / 20))
    r0 = int(round((big["bounds"][3] - win["bounds"][3]) / 20))
    h, w = win["shape"]
    return {k: v[r0:r0 + h, c0:c0 + w] for k, v in arrays.items()}


def judge(poly_utm, win, scenes):
    """scenes: [(date, ids, arrays on win)]. Returns the numbers that go into the evidence."""
    first, looks = bs.season([(d, a) for d, _, a in scenes])
    inside = rasterize([(poly_utm, 1)], out_shape=win["shape"], transform=win["transform"], fill=0, dtype="uint8").astype(bool)
    n = int(inside.sum())
    burnt = int(((first > 0) & inside).sum())
    seen = looks[inside]
    k = np.bincount(first[inside & (first > 0)], minlength=len(scenes))
    when = None
    if burnt:
        j = int(k.argmax())
        when = [scenes[j - 1][0], scenes[j][0]]
    return {
        "pixels": n,
        "burnt_pixels": burnt,
        "burnt_bps": int(round(10_000 * burnt / n)) if n else 0,
        "min_clear_looks": int(seen.min()) if n else 0,
        "burnt_between": when,
    }


def evidence(plot_id, geom_lonlat, ares, win, scenes, numbers):
    return {
        "afterburn": "verdict-evidence/1",
        "plot": plot_id,
        "polygon": geom_lonlat,
        "polygon_hash": polygon_hash(geom_lonlat),
        "ares": ares,
        "window": {"crs": win["crs"], "bounds": [float(v) for v in win["bounds"]], "res_m": 20},
        "scenes": [{"date": d, "items": ids} for d, ids, _ in scenes],
        "catalogue": "https://earth-search.aws.element84.com/v1 (collection sentinel-2-l2a)",
        "rule": bs.RULE,
        "rule_id": bs.RULE_ID,
        **numbers,
    }
