# mon_fires.py
import os
import math
import requests
import datetime

FIRMS_MAP_KEY = os.environ.get("FIRMS_MAP_KEY", "").strip()

# نطاق تقريبي للمملكة + الجوار (تقدر تضبطه)
BBOX_KSA = (34.0, 16.0, 56.5, 33.5)  # (minLon, minLat, maxLon, maxLat)

# مراجع قريبة (مدن/موانئ) لتسمية "قرب ..."
REFS = [
    ("الرياض", 24.7136, 46.6753),
    ("جدة", 21.4858, 39.1925),
    ("مكة", 21.3891, 39.8579),
    ("المدينة", 24.5247, 39.5692),
    ("الدمام", 26.4207, 50.0888),
    ("الجبيل", 27.00, 49.65),
    ("تبوك", 28.3838, 36.5662),
    ("حائل", 27.5114, 41.7208),
    ("عرعر", 30.9753, 41.0381),
    ("العلا", 26.6085, 37.9232),
    ("نيوم", 29.0, 35.0),
]

def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p = math.pi / 180.0
    dlat = (lat2 - lat1) * p
    dlon = (lon2 - lon1) * p
    a = math.sin(dlat/2)**2 + math.cos(lat1*p)*math.cos(lat2*p)*math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def _nearest_ref(lat, lon):
    best = None
    for name, rlat, rlon in REFS:
        d = _haversine_km(lat, lon, rlat, rlon)
        if best is None or d < best[0]:
            best = (d, name)
    if not best:
        return None, None
    return best[1], int(best[0])

def _firms_url():
    # VIIRS SNPP NRT (CSV)
    minLon, minLat, maxLon, maxLat = BBOX_KSA
    # آخر 1 يوم
    return f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{FIRMS_MAP_KEY}/VIIRS_SNPP_NRT/{minLon},{minLat},{maxLon},{maxLat}/1"

def get_events():
    if not FIRMS_MAP_KEY:
        return [{"section": "fires", "title": "ℹ️ FIRMS غير مفعّل: ضع FIRMS_MAP_KEY."}]

    url = _firms_url()
    r = requests.get(url, timeout=45)
    r.raise_for_status()
    text = r.text.strip().splitlines()

    # أول سطر headers
    if len(text) <= 1:
        return [{"section": "fires", "title": "- لا يوجد"}]

    headers = text[0].split(",")
    rows = text[1:]

    def idx(name):
        return headers.index(name)

    i_lat = idx("latitude")
    i_lon = idx("longitude")
    i_frp = idx("frp")
    i_date = idx("acq_date")
    i_time = idx("acq_time")

    points = []
    for line in rows:
        parts = line.split(",")
        try:
            lat = float(parts[i_lat])
            lon = float(parts[i_lon])
            frp = float(parts[i_frp])
            ad = parts[i_date]
            at = parts[i_time]
            # UTC time
            when = f"{ad} {at[:2]}{at[2:]} UTC"
            points.append((frp, lat, lon, when))
        except Exception:
            continue

    if not points:
        return [{"section": "fires", "title": "- لا يوجد"}]

    points.sort(reverse=True, key=lambda x: x[0])
    count = len(points)
    max_frp = points[0][0]

    events = []
    events.append({
        "section": "fires",
        "title": f"🔥 حرائق نشطة داخل السعودية — {count} رصد خلال آخر 24 ساعة (أعلى FRP: {max_frp:.1f})"
    })

    for i, (frp, lat, lon, when) in enumerate(points[:5], start=1):
        ref, dist = _nearest_ref(lat, lon)
        near = f"قرب {ref} (~{dist} كم)" if ref else "موقع غير محدد"
        gmap = f"https://maps.google.com/?q={lat:.5f},{lon:.5f}"
        events.append({
            "section": "fires",
            "title": f"📍 نقطة #{i}: {near} | {lat:.5f},{lon:.5f} | FRP {frp:.1f} | {when} | {gmap}"
        })

    return events
