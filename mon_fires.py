# mon_fires.py
import os
import requests
from datetime import datetime, timezone, timedelta

FIRMS_MAP_KEY = os.environ.get("FIRMS_MAP_KEY", "")
DEBUG_FIRMS = os.environ.get("DEBUG_FIRMS", "0") == "1"

# ✅ صندوق السعودية التقريبي (يمكن تضييقه لاحقًا)
KSA_BBOX = (34.5, 16.0, 55.7, 32.2)  # (min_lon, min_lat, max_lon, max_lat)

SOURCE = os.environ.get("FIRMS_SOURCE", "VIIRS_SNPP_NRT")
DAY_RANGE = int(os.environ.get("FIRMS_DAYS", "1"))  # آخر 24 ساعة

def _firms_url():
    if not FIRMS_MAP_KEY:
        raise RuntimeError("Missing FIRMS_MAP_KEY")
    # API MapKey endpoint (CSV)
    # format: .../api/area/csv/<MAP_KEY>/<SOURCE>/<BBOX>/<DAYS>
    min_lon, min_lat, max_lon, max_lat = KSA_BBOX
    bbox = f"{min_lon},{min_lat},{max_lon},{max_lat}"
    return f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{FIRMS_MAP_KEY}/{SOURCE}/{bbox}/{DAY_RANGE}"

def fetch():
    url = _firms_url()
    if DEBUG_FIRMS:
        print(f"[FIRMS] Requesting: {url}")

    r = requests.get(url, timeout=30)
    r.raise_for_status()
    csv_text = r.text.strip()

    # لو ما فيه بيانات
    if not csv_text or csv_text.count("\n") < 2:
        return [{"section": "fires", "title": "لا يوجد"}]

    lines = csv_text.splitlines()
    header = lines[0].split(",")
    rows = lines[1:]

    # نحاول نجيب الأعمدة المهمّة
    def col(name, default=None):
        try:
            return header.index(name)
        except ValueError:
            return default

    idx_lat = col("latitude")
    idx_lon = col("longitude")
    idx_frp = col("frp")
    idx_date = col("acq_date")
    idx_time = col("acq_time")

    count = len(rows)

    # أعلى FRP
    max_frp = 0.0
    best_latlon = None
    best_time = None

    for row in rows:
        parts = row.split(",")
        try:
            frp = float(parts[idx_frp]) if idx_frp is not None else 0.0
            if frp > max_frp:
                max_frp = frp
                if idx_lat is not None and idx_lon is not None:
                    best_latlon = (float(parts[idx_lat]), float(parts[idx_lon]))
                if idx_date is not None and idx_time is not None:
                    best_time = f"{parts[idx_date]} {parts[idx_time]}"
        except Exception:
            pass

    title = f"🔥 حرائق نشطة داخل السعودية — {count} رصد خلال آخر 24 ساعة (أعلى FRP: {max_frp:.1f})"
    if best_latlon:
        title += f" | أعلى نقطة: {best_latlon[0]:.2f},{best_latlon[1]:.2f}"
    if best_time:
        title += f" | آخر تحديث: {best_time} UTC"

    return [{
        "section": "fires",
        "title": title,
        "count": count
    }]
