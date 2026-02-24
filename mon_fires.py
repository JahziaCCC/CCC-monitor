# mon_fires.py
import os
import math
import datetime
import requests

FIRMS_MAP_KEY = os.environ.get("FIRMS_MAP_KEY", "")
DEBUG_FIRMS = os.environ.get("DEBUG_FIRMS", "0") == "1"

# GitHub Variables (اختياري) - defaults
ALERT_FIRES_COUNT = int(os.environ.get("ALERT_FIRES_COUNT", "200"))
ALERT_FIRES_FRP = float(os.environ.get("ALERT_FIRES_FRP", "80"))
ALERT_FIRES_CLEAR_COUNT = int(os.environ.get("ALERT_FIRES_CLEAR_COUNT", "100"))
ALERT_FIRES_CLEAR_FRP = float(os.environ.get("ALERT_FIRES_CLEAR_FRP", "60"))

# Saudi bbox (تقريباً)
KSA_BBOX = (33.0, 14.8, 57.1, 33.7)  # min_lon, min_lat, max_lon, max_lat

# مرجع مدن (لـ "قرب xxx")
REF_CITIES = {
    "الرياض": (24.7136, 46.6753),
    "مكة": (21.3891, 39.8579),
    "المدينة": (24.5247, 39.5692),
    "جدة": (21.5433, 39.1728),
    "الدمام": (26.4207, 50.0888),
    "الجبيل": (27.0000, 49.6500),
    "بريدة": (26.3592, 43.9818),
    "أبها": (18.2164, 42.5053),
    "جازان": (16.8892, 42.5706),
    "نجران": (17.5650, 44.2289),
    "تبوك": (28.3998, 36.5715),
    "سكاكا": (29.9697, 40.2064),
    "حائل": (27.5114, 41.7208),
    "عرعر": (30.9753, 41.0381),
    "العلا": (26.6083, 37.9232),
    "نيوم": (27.9000, 35.2000),
}

def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    d1 = math.radians(lat2 - lat1)
    d2 = math.radians(lon2 - lon1)
    a = math.sin(d1/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(d2/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def _nearest_city(lat, lon):
    best = None
    for name, (clat, clon) in REF_CITIES.items():
        d = _haversine_km(lat, lon, clat, clon)
        if best is None or d < best[1]:
            best = (name, d)
    return best[0], best[1]

def _fetch_firms_csv():
    if not FIRMS_MAP_KEY:
        return None, "missing_key"

    min_lon, min_lat, max_lon, max_lat = KSA_BBOX
    # VIIRS SNPP NRT (سريع)
    url = (
        "https://firms.modaps.eosdis.nasa.gov/api/area/csv/"
        f"{FIRMS_MAP_KEY}/VIIRS_SNPP_NRT/"
        f"{min_lon},{min_lat},{max_lon},{max_lat}/1"
    )
    if DEBUG_FIRMS:
        print("[FIRMS] Requesting:", url.replace(FIRMS_MAP_KEY, "***"))

    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.text, None

def _parse_csv(text):
    # أول سطر header
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if len(lines) <= 1:
        return []

    header = lines[0].split(",")
    idx = {name: i for i, name in enumerate(header)}

    out = []
    for ln in lines[1:]:
        parts = ln.split(",")
        try:
            lat = float(parts[idx["latitude"]])
            lon = float(parts[idx["longitude"]])
            frp = float(parts[idx.get("frp", -1)]) if "frp" in idx else 0.0
            acq_date = parts[idx.get("acq_date", -1)] if "acq_date" in idx else ""
            acq_time = parts[idx.get("acq_time", -1)] if "acq_time" in idx else ""
            out.append({
                "lat": lat,
                "lon": lon,
                "frp": frp,
                "acq_date": acq_date,
                "acq_time": acq_time
            })
        except Exception:
            continue
    return out

def fetch():
    """
    returns events list for report_official
    - summary event + up to 5 top points
    """
    try:
        csv_text, err = _fetch_firms_csv()
        if err:
            return []

        pts = _parse_csv(csv_text)
        # آخر 24 ساعة تقريباً (API day_range=1 أصلاً)
        count = len(pts)
        if count == 0:
            return [{"section": "fires", "title": "- لا يوجد"}]

        max_frp = max((p["frp"] for p in pts), default=0.0)

        summary_title = f"🔥 حرائق نشطة داخل السعودية — {count} رصد خلال آخر 24 ساعة (أعلى FRP: {max_frp:.1f})"
        events = [{
            "section": "fires",
            "kind": "summary",
            "title": summary_title,
            "count": count,
            "max_frp": max_frp
        }]

        # top 5 by frp
        pts_sorted = sorted(pts, key=lambda x: x["frp"], reverse=True)[:5]
        for i, p in enumerate(pts_sorted, start=1):
            near, dist = _nearest_city(p["lat"], p["lon"])
            maps = f"https://maps.google.com/?q={p['lat']:.5f},{p['lon']:.5f}"
            ts = ""
            if p["acq_date"]:
                # acq_time مثل 1017
                hhmm = p["acq_time"].zfill(4) if p["acq_time"] else ""
                if hhmm:
                    ts = f"{p['acq_date']} {hhmm[:2]}{hhmm[2:]} UTC"
                else:
                    ts = f"{p['acq_date']} UTC"
            line = (
                f"📍 نقطة #{i}: قرب {near} (~{dist:.0f} كم) | "
                f"{p['lat']:.5f},{p['lon']:.5f} | FRP {p['frp']:.1f} | "
                f"{ts} | {maps}"
            )
            events.append({"section": "fires", "title": f"- {line}"})

        return events
    except Exception as e:
        return [{"section": "fires", "title": f"- ⚠️ تعذر جلب بيانات FIRMS: {e}"}]
