# mon_fires.py
import os
import math
import datetime
import requests

FIRMS_MAP_KEY = os.environ.get("FIRMS_MAP_KEY", "").strip()
DEBUG_FIRMS = os.environ.get("DEBUG_FIRMS", "0").strip() == "1"

# مدن/مراكز داخل السعودية لتحديد أقرب مدينة (وسعها لاحقاً)
CITIES = {
    "الرياض": (24.7136, 46.6753),
    "جدة": (21.5433, 39.1728),
    "مكة": (21.3891, 39.8579),
    "المدينة": (24.5247, 39.5692),
    "الدمام": (26.4207, 50.0888),
    "الجبيل": (27.0174, 49.6460),
    "تبوك": (28.3998, 36.5715),
    "حائل": (27.5114, 41.7208),
    "عرعر": (30.9753, 41.0381),
    "سكاكا": (29.9697, 40.2064),
    "جازان": (16.8892, 42.5706),
    "أبها": (18.2164, 42.5053),
    "نجران": (17.5650, 44.2289),
    "الباحة": (20.0129, 41.4677),
    "بريدة": (26.3592, 43.9818),
    "القريات": (31.3314, 37.3428),
    "العلا": (26.6085, 37.9232),
    "نيوم": (29.1977, 35.3050),
}

KSA_BBOX = (14.8, 33.0, 57.1, 33.7)  # جنوب/غرب/شرق/شمال (تقريب)


def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _nearest_city(lat, lon):
    best_name = None
    best_dist = 1e9
    for name, (clat, clon) in CITIES.items():
        d = _haversine_km(lat, lon, clat, clon)
        if d < best_dist:
            best_dist = d
            best_name = name
    return best_name, best_dist


def _in_ksa_bbox(lat, lon):
    south, west, east, north = KSA_BBOX
    return (south <= lat <= north) and (west <= lon <= east)


def collect():
    # لو ما عندك مفتاح، رجع لا يوجد بدل ما يكسر السيستم
    if not FIRMS_MAP_KEY:
        return [{
            "section": "fires",
            "title": "🔥 حرائق الغابات (FIRMS): لا يوجد (FIRMS_MAP_KEY غير مضبوط)."
        }]

    # VIIRS_SNPP_NRT مناسب وسريع عادة
    source = "VIIRS_SNPP_NRT"
    south, west, east, north = KSA_BBOX
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{FIRMS_MAP_KEY}/{source}/{west},{south},{east},{north}/1"

    if DEBUG_FIRMS:
        print(f"[FIRMS] Requesting: {url}")

    r = requests.get(url, timeout=40)
    r.raise_for_status()

    lines = r.text.strip().splitlines()
    if len(lines) <= 1:
        return [{"section": "fires", "title": "- لا يوجد"}]

    header = lines[0].split(",")
    rows = lines[1:]

    # استخراج حقول مهمة
    def idx(col):
        try:
            return header.index(col)
        except Exception:
            return None

    ilat = idx("latitude")
    ilon = idx("longitude")
    ifrp = idx("frp")
    iacq = idx("acq_date")
    itime = idx("acq_time")

    points = []
    for row in rows:
        cols = row.split(",")
        try:
            lat = float(cols[ilat])
            lon = float(cols[ilon])
            frp = float(cols[ifrp]) if ifrp is not None else 0.0
            acq_date = cols[iacq] if iacq is not None else ""
            acq_time = cols[itime] if itime is not None else ""
            points.append((lat, lon, frp, acq_date, acq_time))
        except Exception:
            continue

    # فلترة داخل السعودية تقريبياً
    inside = [p for p in points if _in_ksa_bbox(p[0], p[1])]

    if not inside:
        return [{"section": "fires", "title": "- لا يوجد"}]

    inside.sort(key=lambda x: x[2], reverse=True)
    top_frp = inside[0][2]
    count = len(inside)

    # ملخص
    events = []
    events.append({
        "section": "fires",
        "title": f"🔥 حرائق نشطة داخل السعودية — {count} رصد خلال آخر 24 ساعة (أعلى FRP: {top_frp:.1f})",
        "meta": {"count": count, "top_frp": top_frp}
    })

    # أفضل 5 نقاط
    now_utc = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    for i, (lat, lon, frp, acq_date, acq_time) in enumerate(inside[:5], start=1):
        city, dist = _nearest_city(lat, lon)
        when = f"{acq_date} {acq_time} UTC".strip()
        gmap = f"https://maps.google.com/?q={lat:.5f},{lon:.5f}"
        events.append({
            "section": "fires",
            "title": f"📍 نقطة #{i}: قرب {city} (~{dist:.0f} كم) | {lat:.5f},{lon:.5f} | FRP {frp:.1f} | {when} | {gmap}"
        })

    return events
