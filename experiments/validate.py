"""Validate the rule against an independent sensor: NASA FIRMS VIIRS fire detections (13:30 / 01:30 IST passes).

For each VIIRS detection between two Sentinel-2 passes, how much of the harvested land inside its 375 m footprint
does the rule call burnt in that interval? Compare with random harvested land. If the rule finds burns, VIIRS
footprints should hold more of them. Also reports how many rule scars have no VIIRS detection near them.
"""
import json
import os
import sys

import numpy as np
from pyproj import Transformer
from scipy import ndimage as ndi
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))
import burnscar as bs  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")


def viirs_points(seen, before, after, passtime="0550"):
    st = json.load(open(f"{ROOT}/data/study.json"))
    T = st["grid"]["transform"]
    tr = Transformer.from_crs("EPSG:4326", st["grid"]["crs"], always_xy=True)
    pts = []
    for d in json.load(open(f"{ROOT}/data/viirs.json")):
        if (before, passtime) < (d["date"], d["time"]) < (after, passtime):
            x, y = tr.transform(d["lon"], d["lat"])
            r, c = (y - T[5]) / T[4], (x - T[2]) / T[0]
            if 0 <= r < seen.shape[0] and 0 <= c < seen.shape[1] and seen[int(r), int(c)]:
                pts.append((r, c))
    return np.array(pts)


def footprint_share(m, harv, rc, rad=9):
    """Burnt share of harvested land within 9 px of 20 m (a 375 m VIIRS footprint) of each point."""
    out = []
    for r, c in rc:
        r, c = int(r), int(c)
        sl = (slice(max(0, r - rad), r + rad + 1), slice(max(0, c - rad), c + rad + 1))
        h = harv[sl]
        out.append(m[sl][h].mean() if h.sum() > 20 else np.nan)
    return np.array(out)


def lift(m, harv, before, after):
    pts = viirs_points(harv, before, after)
    hv = np.argwhere(harv)
    rnd = hv[np.random.default_rng(1).choice(len(hv), 4000, replace=False)]
    a, b = footprint_share(m, harv, pts), footprint_share(m, harv, rnd)
    return {"in_viirs_footprints": round(float(np.nanmean(a)), 3), "random_harvested": round(float(np.nanmean(b)), 3), "lift": round(float(np.nanmean(a) / np.nanmean(b)), 2)}


def main(before="2026-10-13", after="2026-10-18", passtime="0550"):
    st = json.load(open(f"{ROOT}/data/study.json"))
    T = st["grid"]["transform"]
    pre, post = (dict(np.load(f"{ROOT}/data/s2_{d}.npz")) for d in (before, after))
    m, seen = bs.burnt_between(pre, post)
    harv = seen & (bs.indices(post)["NDVI"] < bs.RULE["harvested_ndvi_max"])
    tr = Transformer.from_crs("EPSG:4326", st["grid"]["crs"], always_xy=True)
    viirs = json.load(open(f"{ROOT}/data/viirs.json"))
    pts = []
    for d in viirs:
        if (before, passtime) < (d["date"], d["time"]) < (after, passtime):
            x, y = tr.transform(d["lon"], d["lat"])
            r, c = (y - T[5]) / T[4], (x - T[2]) / T[0]
            if 0 <= r < m.shape[0] and 0 <= c < m.shape[1] and seen[int(r), int(c)]:
                pts.append((r, c))
    pts = np.array(pts)
    rng = np.random.default_rng(1)
    hv = np.argwhere(harv)
    rnd = hv[rng.choice(len(hv), 4000, replace=False)]

    def share(rc, rad=9):  # 9 px of 20 m: a 375 m VIIRS footprint
        out = []
        for r, c in rc:
            r, c = int(r), int(c)
            sl = (slice(max(0, r - rad), r + rad + 1), slice(max(0, c - rad), c + rad + 1))
            h = harv[sl]
            out.append(m[sl][h].mean() if h.sum() > 20 else np.nan)
        return np.array(out)

    a, b = share(pts), share(rnd)
    lab, n = ndi.label(m)
    sizes = ndi.sum(m, lab, range(1, n + 1))
    cent = np.array(ndi.center_of_mass(m, lab, range(1, n + 1)))
    dist, _ = cKDTree(pts).query(cent)
    res = {
        "interval": [before, after],
        "rule_id": bs.RULE_ID,
        "clear_land_ha": round(float(seen.sum()) * 0.04),
        "harvested_ha": round(float(harv.sum()) * 0.04),
        "burnt_ha": round(float(m.sum()) * 0.04),
        "scars": int(n),
        "viirs_detections": int(len(pts)),
        "burnt_share_in_viirs_footprints": round(float(np.nanmean(a)), 3),
        "burnt_share_random_harvested": round(float(np.nanmean(b)), 3),
        "lift": round(float(np.nanmean(a) / np.nanmean(b)), 2),
        "scars_with_viirs_within_375m": round(float(np.mean(dist <= 18.75)), 3),
        "scars_with_viirs_within_750m": round(float(np.mean(dist <= 37.5)), 3),
        "flames_at_after_pass_px": int(bs.flames(post).sum()),
    }
    # flames Sentinel-2 caught at the after pass (one point per fire, kilns excluded) vs VIIRS the same day
    L = json.load(open(f"{ROOT}/docs/data/layers.json"))
    fl = np.array([tr.transform(f["lon"], f["lat"]) for f in L["flames"] if f["date"] == after])
    same = np.array([tr.transform(d["lon"], d["lat"]) for d in viirs if d["date"] == after])
    if len(fl) and len(same):
        dd, _ = cKDTree(same).query(fl)
        res["s2_fires_at_after_pass"] = int(len(fl))
        res["s2_fires_with_viirs_same_day_within_1km"] = round(float(np.mean(dd <= 1000)), 3)
    print(json.dumps(res, indent=1))
    json.dump(res, open(f"{ROOT}/docs/data/validation.json", "w"), indent=1)
    return res


if __name__ == "__main__":
    main(*sys.argv[1:])
