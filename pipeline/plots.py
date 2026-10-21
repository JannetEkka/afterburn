"""Build the demo pact: pick real fields in three villages, judge each, and write the evidence files.

Run after the season arrays exist (data/s2_*.npz). Writes docs/data/plots.json and docs/evidence/plot-N.json.
"""
import json
import os
import sys

import numpy as np
from pyproj import Transformer
from rasterio.features import rasterize
from shapely.geometry import mapping, shape
from shapely.ops import transform as shp_transform  # noqa: shapely 2 still ships it

import burnscar as bs
import verdict as vd

ROOT = os.path.join(os.path.dirname(__file__), "..")
VILLAGES = {
    "A": "Village A, Kapurthala district",
    "B": "Village B, Tarn Taran district",
    "C": "Village C, Kapurthala district",
}
PER_VILLAGE = 8


def main():
    st = json.load(open(f"{ROOT}/data/study.json"))
    big = st["grid"]
    dates = json.load(open(f"{ROOT}/data/season_dates.json"))
    arrays = {d: dict(np.load(f"{ROOT}/data/s2_{d}.npz")) for d in dates}
    segs = json.load(open(f"{ROOT}/data/_segments.json"))
    to_ll = Transformer.from_crs(vd.CRS, "EPSG:4326", always_xy=True)
    last = arrays[dates[-1]]
    ndvi_last = (last["B8A"] - last["B04"]) / (last["B8A"] + last["B04"])

    candidates = {}
    for v, s in segs.items():
        rows = []
        for g in s["polys_utm"]:
            # judge the polygon exactly as it will be published (lon/lat, 6 decimals), so a recheck from the
            # evidence file lands on the same window and the same pixels
            ll = mapping(shp_transform(lambda x, y, z=None: to_ll.transform(x, y), shape(g)))
            ll = {"type": "Polygon", "coordinates": [[[round(x, 6), round(y, 6)] for x, y in ring] for ring in ll["coordinates"]]}
            p = vd.to_utm(ll)
            win = vd.window(p)
            scenes = [(d, st["dates"][d], vd.crop(arrays[d], big, win)) for d in dates]
            nums = vd.judge(p, win, scenes)
            inside = rasterize([(p, 1)], out_shape=win["shape"], transform=win["transform"], fill=0, dtype="uint8").astype(bool)
            ndvi = np.nanmean(vd.crop({"n": ndvi_last}, big, win)["n"][inside])
            if nums["pixels"] < 12 or ndvi >= 0.35 or nums["min_clear_looks"] < 2:
                continue  # too small, not harvested yet, or not seen often enough
            rows.append((ll, p, win, scenes, nums))
        candidates[v] = rows
        print(v, "harvested candidates", len(rows), "burnt", sum(r[4]["burnt_bps"] >= 2000 for r in rows), file=sys.stderr)

    rng = np.random.default_rng(42)
    picked = []
    for v, rows in candidates.items():
        burnt = [r for r in rows if r[4]["burnt_bps"] >= 2000]
        clean = [r for r in rows if r[4]["burnt_bps"] < 2000]
        nb = {"A": 0, "B": 1, "C": 3}[v]
        nb = min(nb, len(burnt))
        take = [burnt[i] for i in rng.choice(len(burnt), nb, replace=False)] if nb else []
        take += [clean[i] for i in rng.choice(len(clean), min(PER_VILLAGE - nb, len(clean)), replace=False)]
        # west to east, so plot numbers read across the map
        take.sort(key=lambda r: r[1].centroid.x)
        picked += [(v, *r) for r in take]

    os.makedirs(f"{ROOT}/docs/evidence", exist_ok=True)
    out = []
    taken = set()
    for n, (v, ll, p, win, scenes, nums) in enumerate(picked, start=1):
        ares = int(round(p.area / 100))
        cells = vd.cells(p)
        assert cells and not (set(cells) & taken), f"plot {n} has no cells or overlaps"
        taken |= set(cells)
        ev = vd.evidence(n, ll, ares, win, scenes, nums)
        blob = vd.canonical(ev)
        open(f"{ROOT}/docs/evidence/plot-{n}.json", "wb").write(blob)
        out.append({
            "plot": n,
            "village": v,
            "village_name": VILLAGES[v],
            "village_id": vd.keccak256(f"afterburn-demo/{v}".encode()),
            "polygon": ll,
            "polygon_hash": ev["polygon_hash"],
            "ares": ares,
            "cells": [str(c) for c in cells],
            "burnt_bps": nums["burnt_bps"],
            "burnt_between": nums["burnt_between"],
            "evidence_hash": vd.keccak256(blob),
            "evidence_uri": f"evidence/plot-{n}.json",
        })
    os.makedirs(f"{ROOT}/docs/data", exist_ok=True)
    json.dump({"rule": bs.RULE, "rule_id": bs.RULE_ID, "season": dates, "plots": out}, open(f"{ROOT}/docs/data/plots.json", "w"), indent=1)
    for o in out:
        print(o["plot"], o["village"], o["ares"], "ares", len(o["cells"]), "cells", "burnt", o["burnt_bps"] / 100, "%", o["burnt_between"])


if __name__ == "__main__":
    main()
