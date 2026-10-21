"""Draw demo plots on real fields: segment a village window of 10 m Sentinel-2 imagery into fields.

These are real fields cut from the imagery, so their verdicts are real. Nobody enrolled them: the farmers, their
payout addresses and the enrolment are simulated for the demo.
"""
import numpy as np
from rasterio.features import shapes
from shapely.geometry import shape, mapping
from skimage.segmentation import felzenszwalb

import s2


def segment(items_by_date, bbox, scale=120, min_px=50):
    """Fields from two dates (field edges show up best when one side is harvested and the other isn't)."""
    g = s2.utm_grid(bbox, res=10)
    layers = []
    for its in items_by_date:
        z = s2.read_grid(its, g)
        for b in ("B04", "B03", "B02", "B8A", "B11"):
            v = np.nan_to_num(z[b])
            layers.append((v - np.percentile(v, 2)) / (np.percentile(v, 98) - np.percentile(v, 2) + 1e-6))
    img = np.clip(np.dstack(layers), 0, 1)
    seg = felzenszwalb(img, scale=scale, sigma=0.6, min_size=min_px, channel_axis=2)
    polys = []
    from rasterio import Affine
    T = Affine(*g["transform"])
    for geom, val in shapes(seg.astype(np.int32), transform=T):
        p = shape(geom).simplify(5)
        if p.is_valid and not p.is_empty:
            polys.append(p)
    return polys, g
