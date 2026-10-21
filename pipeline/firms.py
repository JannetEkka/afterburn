"""NASA FIRMS active-fire detections: the official fire count, from VIIRS on Suomi-NPP, NOAA-20 and NOAA-21.

The 7-day files need no key. VIIRS crosses Punjab at about 13:30 and 01:30 IST, so a fire lit at 4 pm and out by
midnight is never in them.
"""
import csv
import io
import urllib.request

URL = "https://firms.modaps.eosdis.nasa.gov/data/active_fire/{p}/csv/{f}_South_Asia_7d.csv"
SOURCES = {
    "VIIRS S-NPP": ("suomi-npp-viirs-c2", "SUOMI_VIIRS_C2"),
    "VIIRS NOAA-20": ("noaa-20-viirs-c2", "J1_VIIRS_C2"),
    "VIIRS NOAA-21": ("noaa-21-viirs-c2", "J2_VIIRS_C2"),
}


def fetch(bbox, cache=None):
    """All VIIRS detections in the last 7 days inside bbox = [W, S, E, N]."""
    out = []
    for sat, (p, f) in SOURCES.items():
        text = urllib.request.urlopen(URL.format(p=p, f=f), timeout=120).read().decode()
        for r in csv.DictReader(io.StringIO(text)):
            lat, lon = float(r["latitude"]), float(r["longitude"])
            if bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]:
                out.append({"sat": sat, "lat": lat, "lon": lon, "date": r["acq_date"], "time": r["acq_time"], "frp": float(r["frp"]), "conf": r["confidence"]})
    return out


def merge(old, new):
    """Keep detections across runs: the files only hold 7 days."""
    key = lambda d: (d["sat"], d["date"], d["time"], round(d["lat"], 5), round(d["lon"], 5))
    seen = {key(d): d for d in old}
    for d in new:
        seen.setdefault(key(d), d)
    return sorted(seen.values(), key=lambda d: (d["date"], d["time"]))
