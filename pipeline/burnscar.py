"""The burn-scar rule: which harvested fields burned between two clear Sentinel-2 passes.

A fire leaves a scar for days, whatever hour it was lit. Between the pass before and the pass after, a burnt
field (a) has no green crop, (b) gets darker, and (c) its Mid-Infrared Burn Index rises: char brightens the
2.2 um band against the 1.6 um band. MIRBI is the index ISRO's National Remote Sensing Centre uses for burnt
area. Ploughed or irrigated fields darken too, but their MIRBI rises far less.

The rule is a handful of thresholds on public bands, so anyone can recompute a verdict exactly. That matters more
here than a few points of accuracy: a farmer's money depends on it.
"""
import hashlib
import json

import numpy as np
from scipy import ndimage as ndi

RULE = {
    "name": "afterburn-scar",
    "version": 2,
    "harvested_ndvi_max": 0.35,  # after-pass NDVI: no green crop left
    "mirbi_rise_min": 0.25,  # MIRBI(after) - MIRBI(before)
    "mirbi_after_min": 1.6,  # char level: 10th percentile of fresh char next to fires Sentinel-2 caught burning.
    # Ploughed wet soil also darkens and lifts MIRBI from a green crop, but stays near 1.5.
    "swir1_drop_min": 0.02,  # B11(before) - B11(after)
    "vis_max": 0.10,  # mean of B02, B03, B04 after: dark
    "nir_max": 0.25,  # B8A after: dark
    "smooth_px": 3,  # 3x3 median filter on the mask
    "min_patch_px": 10,  # 10 pixels of 20 m = 0.4 ha
    "clear_scl": [4, 5, 6, 7],  # Sentinel-2 scene classes that count as a clear view
    "haze_b02_p10_max": 0.05,  # dark-object test: in a clear scene the darkest tenth of pixels is dark in blue
}
RULE_ID = hashlib.sha256(json.dumps(RULE, sort_keys=True).encode()).hexdigest()[:16]


def indices(z):
    B4, B8, B11, B12 = z["B04"], z["B8A"], z["B11"], z["B12"]
    with np.errstate(invalid="ignore", divide="ignore"):
        return {
            "VIS": (z["B02"] + z["B03"] + B4) / 3,
            "NIR": B8,
            "S1": B11,
            "NDVI": (B8 - B4) / (B8 + B4),
            "MIRBI": 10 * B12 - 9.8 * B11 + 2,
        }


def clear(z):
    return np.isin(z["SCL"], RULE["clear_scl"]) & np.isfinite(z["B12"]) & np.isfinite(z["B02"])


def usable(z):
    """Whole-scene haze check. Smoke haze over Punjab in October brightens every pixel, which hides the darkening
    the rule looks for, so a hazy pass is skipped rather than compared."""
    ok = clear(z)
    return ok.mean() > 0.05 and float(np.nanpercentile(z["B02"][ok], 10)) <= RULE["haze_b02_p10_max"]


def burnt_between(before, after):
    """Boolean mask of pixels that burned between two passes, and the mask of pixels clear in both."""
    a, b = indices(after), indices(before)
    seen = clear(before) & clear(after)
    with np.errstate(invalid="ignore"):
        m = (
            (a["NDVI"] < RULE["harvested_ndvi_max"])
            & (a["MIRBI"] - b["MIRBI"] >= RULE["mirbi_rise_min"])
            & (a["MIRBI"] >= RULE["mirbi_after_min"])
            & (b["S1"] - a["S1"] >= RULE["swir1_drop_min"])
            & (a["VIS"] <= RULE["vis_max"])
            & (a["NIR"] <= RULE["nir_max"])
            & seen
        )
    m = ndi.median_filter(m.astype(np.uint8), size=RULE["smooth_px"]).astype(bool)
    lab, n = ndi.label(m)
    if n:
        sizes = ndi.sum(m, lab, range(1, n + 1))
        m = np.r_[False, sizes >= RULE["min_patch_px"]][lab]
    return m, seen


def flames(z):
    """Pixels on fire at the moment of the pass (11:20 IST): SWIR-2 at least 1.5x SWIR-1 and above NIR.
    Dry straw is bright in SWIR too, but never this lopsided."""
    with np.errstate(invalid="ignore", divide="ignore"):
        return (z["B12"] / np.maximum(z["B11"], 1e-3) > 1.5) & (z["B12"] > 0.25) & (z["B12"] > z["B8A"])


def season(scenes):
    """scenes: [(date, arrays)] sorted by date, usable() ones only. Each pixel is compared with its own last clear view, so a cloudy
    pass doesn't hide a burn. Returns the index of the scene in which each pixel first showed a burn (-1 = never)
    and how many clear looks each pixel had after the first scene."""
    bands = ["B02", "B03", "B04", "B8A", "B11", "B12"]
    first = np.full(scenes[0][1]["B12"].shape, -1, np.int16)
    looks = np.zeros_like(first)
    ok = clear(scenes[0][1])
    last = {b: np.where(ok, scenes[0][1][b], np.nan) for b in bands}
    for k in range(1, len(scenes)):
        cur = scenes[k][1]
        prev = dict(last, SCL=np.where(np.isfinite(last["B12"]), 4, 0).astype(np.uint8))
        m, seen = burnt_between(prev, cur)
        first[(first < 0) & m] = k
        looks += seen
        ok = clear(cur)
        for b in bands:
            last[b] = np.where(ok, cur[b], last[b])
    return first, looks
