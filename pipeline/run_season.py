"""Fetch the season's Sentinel-2 passes and VIIRS detections for the study area, map the scars, and export the
layers the site shows. Re-run it after each new pass; it only downloads what it doesn't have.

    python pipeline/run_season.py            # then: plots.py, chips.py, notices.py, ../experiments/validate.py
"""
import collections
import json
import os
import sys

import numpy as np
from PIL import Image
from pyproj import Transformer
from rasterio import Affine
from rasterio.warp import Resampling, calculate_default_transform, reproject
from scipy import ndimage as ndi

import burnscar as bs
import firms
import s2

ROOT = os.path.join(os.path.dirname(__file__), "..")
BBOX = [74.65, 31.15, 75.45, 31.62]  # Amritsar, Tarn Taran, Kapurthala
TILES = ["43RDQ", "43REQ"]
START = "2026-09-20"
COLOURS = [(255, 196, 0), (255, 112, 0), (220, 20, 60), (150, 0, 90), (90, 0, 120)]


def fetch_scenes(end):
    path = f"{ROOT}/data/study.json"
    st = json.load(open(path)) if os.path.exists(path) else {"bbox": BBOX, "grid": s2.utm_grid(BBOX), "dates": {}}
    for d, its in s2.search(BBOX, START, end, tiles=TILES, max_cloud=45).items():
        if os.path.exists(f"{ROOT}/data/s2_{d}.npz"):
            continue
        print("reading", d, [i["id"] for i in its], file=sys.stderr)
        np.savez_compressed(f"{ROOT}/data/s2_{d}.npz", **s2.read_grid(its, st["grid"]))
        st["dates"][d] = [i["id"] for i in its]
    json.dump(st, open(path, "w"), indent=1)
    return st


def update_viirs():
    path = f"{ROOT}/data/viirs.json"
    old = json.load(open(path)) if os.path.exists(path) else []
    allp = firms.merge(old, firms.fetch(BBOX))
    json.dump(allp, open(path, "w"))
    return allp


def season_map(st):
    usable = []
    for d in sorted(st["dates"]):
        z = dict(np.load(f"{ROOT}/data/s2_{d}.npz"))
        if bs.usable(z):
            usable.append((d, z))
        else:
            print("skipping cloudy or hazy pass", d, file=sys.stderr)
    first, looks = bs.season(usable)
    np.save(f"{ROOT}/data/first_burn.npy", first)
    np.save(f"{ROOT}/data/looks.npy", looks)
    json.dump([d for d, _ in usable], open(f"{ROOT}/data/season_dates.json", "w"))
    return usable, first


def export_layers(st, usable, first, viirs):
    g = st["grid"]
    l, b, r, t = g["bounds"]
    dst_T, w, h = calculate_default_transform(g["crs"], "EPSG:4326", first.shape[1], first.shape[0], l, b, r, t)
    dst = np.full((h, w), -1, np.int16)
    reproject(first, dst, src_transform=Affine(*g["transform"]), src_crs=g["crs"], dst_transform=dst_T, dst_crs="EPSG:4326",
              resampling=Resampling.nearest, src_nodata=-1, dst_nodata=-1)
    rgba = np.zeros((h, w, 4), np.uint8)
    for k in range(1, len(usable)):
        m = dst == k
        rgba[m, :3] = COLOURS[(k - 1) % len(COLOURS)]
        rgba[m, 3] = 235
    os.makedirs(f"{ROOT}/docs/data", exist_ok=True)
    Image.fromarray(rgba).save(f"{ROOT}/docs/data/scars.png", optimize=True)

    # fires Sentinel-2 caught in flames: one point per fire; spots that burn on several passes are brick kilns
    T = g["transform"]
    inv = Transformer.from_crs(g["crs"], "EPSG:4326", always_xy=True)
    F = {d: bs.flames(z) for d, z in usable}
    flames = []
    for d in F:
        other = np.zeros_like(F[d])
        for e in F:
            if e != d:
                other |= F[e]
        f = F[d] & ~ndi.binary_dilation(other, iterations=3)
        lab, n = ndi.label(f, structure=np.ones((3, 3)))
        for rr, cc in ndi.center_of_mass(f, lab, range(1, n + 1)):
            lo, la = inv.transform(T[2] + (cc + 0.5) * T[0], T[5] + (rr + 0.5) * T[4])
            flames.append({"date": d, "lat": round(la, 5), "lon": round(lo, 5)})

    ds = [d for d, _ in usable]
    W, N = dst_T.c, dst_T.f
    layers = {
        "overlay_bounds": [[N + dst_T.e * h, W], [N, W + dst_T.a * w]],
        "season": ds,
        "intervals": [{"from": ds[k - 1], "to": ds[k], "colour": "#%02x%02x%02x" % COLOURS[(k - 1) % len(COLOURS)],
                       "burnt_ha": round(float((first == k).sum()) * 0.04)} for k in range(1, len(ds))],
        "season_burnt_ha": round(float((first > 0).sum()) * 0.04),
        "land_ha": round(first.size * 0.04),
        "viirs": [{k: v[k] for k in ("lat", "lon", "date", "time", "sat")} for v in viirs],
        "flames": flames,
    }
    json.dump(layers, open(f"{ROOT}/docs/data/layers.json", "w"))
    print({i["from"] + ">" + i["to"]: i["burnt_ha"] for i in layers["intervals"]}, "season", layers["season_burnt_ha"], "ha;",
          "flames by pass", dict(collections.Counter(f["date"] for f in flames)), file=sys.stderr)


def main():
    import datetime
    end = datetime.date.today().isoformat()
    st = fetch_scenes(end)
    viirs = update_viirs()
    usable, first = season_map(st)
    export_layers(st, usable, first, viirs)


if __name__ == "__main__":
    main()
