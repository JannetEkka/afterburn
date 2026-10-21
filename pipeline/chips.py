"""Before/after true-colour chips of each plot, for the site and the deck.

Each chip is saved at Sentinel-2's own 10 m resolution as a lossless PNG, one image pixel per satellite pixel, so the
browser can scale it up as crisp squares instead of smearing it. The plot outline is written separately as pixel
coordinates (docs/data/chips.json) and drawn as a vector on top, so it stays sharp at any size.
"""
import json
import os
import sys

import numpy as np
from PIL import Image

import s2
import verdict as vd

ROOT = os.path.join(os.path.dirname(__file__), "..")


def rgb(z):
    a = np.dstack([z["B04"], z["B03"], z["B02"]])
    return (np.clip(np.nan_to_num(a) / 0.22, 0, 1) ** 0.75 * 255).astype(np.uint8)


def main():
    st = json.load(open(f"{ROOT}/data/study.json"))
    plots = json.load(open(f"{ROOT}/docs/data/plots.json"))
    os.makedirs(f"{ROOT}/docs/chips", exist_ok=True)
    items = {d: s2.items(st["dates"][d]) for d in plots["season"]}
    meta = {}
    for p in plots["plots"]:
        poly = vd.to_utm(p["polygon"])
        win = vd.window(poly, res=10)
        l, b, r, t = win["bounds"]
        h, w = win["shape"]
        ring = [[round((x - l) / 10, 2), round((t - y) / 10, 2)] for x, y in poly.exterior.coords]
        meta[p["plot"]] = {"w": w, "h": h, "ring": ring}
        for d in plots["season"]:
            z = s2.read_grid(items[d], win, bands=("B02", "B03", "B04"))
            Image.fromarray(rgb(z)).save(f"{ROOT}/docs/chips/plot-{p['plot']}-{d}.png", optimize=True)
        print("plot", p["plot"], file=sys.stderr)
    json.dump(meta, open(f"{ROOT}/docs/data/chips.json", "w"))


if __name__ == "__main__":
    main()
