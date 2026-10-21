"""Read Sentinel-2 L2A bands for a lon/lat box from the public Earth Search catalogue (AWS open data).

Every read is a byte-range request on a cloud-optimised GeoTIFF, so a 40 km box costs a few MB, not the 1 GB scene.
"""
import json
import os
import urllib.request

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
if os.path.exists("/root/.ccr/ca-bundle.crt"):
    os.environ.setdefault("CURL_CA_BUNDLE", "/root/.ccr/ca-bundle.crt")

STAC = "https://earth-search.aws.element84.com/v1/search"
# Earth Search asset names -> Sentinel-2 band names
BANDS = {"blue": "B02", "green": "B03", "red": "B04", "nir08": "B8A", "swir16": "B11", "swir22": "B12", "scl": "SCL"}


def search(bbox, start, end, tiles=None, max_cloud=60):
    body = {"collections": ["sentinel-2-l2a"], "bbox": bbox, "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z", "limit": 100}
    req = urllib.request.Request(STAC, json.dumps(body).encode(), {"content-type": "application/json"})
    items = json.load(urllib.request.urlopen(req, timeout=60))["features"]
    if tiles:
        items = [i for i in items if i["id"].split("_")[1] in tiles]
    # group by date; per tile keep the latest processing run (the _N suffix)
    by_date = {}
    for i in sorted(items, key=lambda i: i["id"]):
        by_date.setdefault(i["properties"]["datetime"][:10], {})[i["id"].split("_")[1]] = i
    dates = {}
    for d, per_tile in sorted(by_date.items()):
        its = list(per_tile.values())
        cloud = np.mean([i["properties"].get("eo:cloud_cover", 100) for i in its])
        if cloud <= max_cloud:
            dates[d] = its
    return dates


def utm_grid(bbox, crs="EPSG:32643", res=20):
    """A fixed 20 m grid over the box, snapped to the Sentinel-2 pixel grid, so scenes and tiles line up pixel for pixel."""
    l, b, r, t = transform_bounds("EPSG:4326", crs, *bbox)
    l, b = np.floor(l / res) * res, np.floor(b / res) * res
    r, t = np.ceil(r / res) * res, np.ceil(t / res) * res
    shape = (int((t - b) / res), int((r - l) / res))
    return {"crs": crs, "transform": (res, 0.0, l, 0.0, -res, t), "shape": shape, "bounds": (l, b, r, t)}


def read_grid(items, grid, bands=None):
    """Read every band of one date onto the grid, filling from each tile in turn (tiles of one UTM zone share a pixel grid)."""
    l, b, r, t = grid["bounds"]
    want = {a: b for a, b in BANDS.items() if bands is None or b in bands}
    out = {band: None for band in want.values()}
    for item in items:
        for asset, band in want.items():
            href = item["assets"][asset]["href"]
            with rasterio.open(href) as src:
                assert str(src.crs) == grid["crs"], (src.crs, grid["crs"])
                w = from_bounds(l, b, r, t, transform=src.transform).round_offsets().round_lengths()
                rs = Resampling.nearest if band == "SCL" else Resampling.average
                a = src.read(1, window=w, out_shape=grid["shape"], resampling=rs, boundless=True, fill_value=0)
            if band == "SCL":
                v = a.astype(np.uint8)
                out[band] = v if out[band] is None else np.where(out[band] == 0, v, out[band])
            else:
                rb = (item["assets"][asset].get("raster:bands") or [{}])[0]
                # Earth Search has already removed the -1000 BOA offset when this flag is set, even though
                # raster:bands still lists offset -0.1; applying it again makes vegetation red negative.
                offset = 0.0 if item["properties"].get("earthsearch:boa_offset_applied") else rb.get("offset", 0.0)
                v = a.astype(np.float32) * rb.get("scale", 1e-4) + offset
                v[a == rb.get("nodata", 0)] = np.nan
                out[band] = v if out[band] is None else np.where(np.isnan(out[band]), v, out[band])
    return out


def items(ids):
    """STAC items by id, in the order given."""
    body = {"collections": ["sentinel-2-l2a"], "ids": list(ids), "limit": len(ids)}
    req = urllib.request.Request(STAC, json.dumps(body).encode(), {"content-type": "application/json"})
    got = {i["id"]: i for i in json.load(urllib.request.urlopen(req, timeout=60))["features"]}
    return [got[i] for i in ids]
