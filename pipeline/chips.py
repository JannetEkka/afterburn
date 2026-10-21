"""Before/after true-colour chips of each plot at 10 m, with the plot outlined. For the site and the deck."""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw
from rasterio.features import rasterize
from scipy import ndimage as ndi
from shapely.geometry import shape

import s2
import verdict as vd

ROOT = os.path.join(os.path.dirname(__file__), "..")


def rgb(z):
    a = np.dstack([z["B04"], z["B03"], z["B02"]])
    return (np.clip(np.nan_to_num(a) / 0.22, 0, 1) ** 0.75 * 255).astype(np.uint8)


def main(scale=6):
    st = json.load(open(f"{ROOT}/data/study.json"))
    plots = json.load(open(f"{ROOT}/docs/data/plots.json"))
    os.makedirs(f"{ROOT}/docs/chips", exist_ok=True)
    items = {d: s2.items(st["dates"][d]) for d in plots["season"]}
    for p in plots["plots"]:
        poly = vd.to_utm(p["polygon"])
        win = vd.window(poly, res=10)
        edge = rasterize([(poly, 1)], out_shape=win["shape"], transform=win["transform"], fill=0, dtype="uint8").astype(bool)
        edge = edge & ~ndi.binary_erosion(edge)
        for d in plots["season"]:
            z = s2.read_grid(items[d], win, bands=("B02", "B03", "B04"))
            im = Image.fromarray(rgb(z)).resize((win["shape"][1] * scale, win["shape"][0] * scale), Image.NEAREST)
            dr = ImageDraw.Draw(im)
            for y, x in zip(*np.nonzero(edge)):
                dr.rectangle([x * scale, y * scale, x * scale + scale - 1, y * scale + scale - 1], outline=(0, 230, 255))
            im.save(f"{ROOT}/docs/chips/plot-{p['plot']}-{d}.jpg", quality=85)
        print("plot", p["plot"], file=sys.stderr)


if __name__ == "__main__":
    main()
