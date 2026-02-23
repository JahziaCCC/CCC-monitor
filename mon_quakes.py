import requests
from datetime import datetime, timedelta, timezone

# =====================================
# USGS Earthquake Catalog API (GeoJSON)
# https://earthquake.usgs.gov/fdsnws/event/1/
# =====================================

MIN_MAG_SA = 3.0
LOOKBACK_HOURS = 24

# حدود السعودية (تقريبية - لتقليل النتائج فقط)
# ملاحظة: هذا وحده لا يكفي لأن بعض الأحداث في دول مجاورة قد تقع داخل صندوق الإحداثيات
SA_BBOX = {
    "minlatitude": 16.0,
    "maxlatitude": 32.5,
    "minlongitude": 34.0,
    "maxlongitude": 56.0,
}

# كلمات تساعدنا نؤكد أن الحدث داخل السعودية من نص "place"
SAUDI_KEYWORDS = [
    "saudi arabia",
    "saudi",
    "ksa",
    "kingdom of saudi arabia",
]

def _query_usgs():
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=LOOKBACK_HOURS)

    url = "https://earthquake.usgs.gov/fdsnws/event/1/query"
    params = {
        "format": "geojson",
        "starttime": start_time.strftime("%Y-%m-%dT%H:%M:%S"),
        "endtime": end_time.strftime("%Y-%m-%dT%H:%M:%S"),
        "minmagnitude": MIN_MAG_SA,
        "orderby": "time",
        **SA_BBOX,
    }

    try:
        r = requests.get(url, params=params, timeout=25)
        r.raise_for_status()
        data = r.json()
        return data.get("features", [])
    except Exception:
        return []

def _is_saudi_place(place: str) -> bool:
    if not place:
        return False
    p = place.lower()
    return any(k in p for k in SAUDI_KEYWORDS)

def fetch():
    """
    واجهة متوافقة مع main.py (لازم اسمها fetch)
    ترجع list من events بصيغة النظام
    - داخل السعودية فقط
    - Magnitude >= 3.0
    """
    events = []
    features = _query_usgs()

    for f in features:
        props = f.get("properties", {}) or {}
        geom = f.get("geometry", {}) or {}
        coords = geom.get("coordinates", [])

        if len(coords) < 2:
            continue

        lon, lat = float(coords[0]), float(coords[1])

        mag = props.get("mag")
        if mag is None:
            continue
        try:
            mag = float(mag)
        except Exception:
            continue
        if mag < MIN_MAG_SA:
            continue

        place = props.get("place") or ""

        # ✅ فلترة “داخل السعودية فقط” اعتمادًا على وصف المكان
        # هذا يمنع حالات مثل: "Mohr, Iran" من الظهور كداخل السعودية
        if not _is_saudi_place(place):
            continue

        t_ms = props.get("time")
        if t_ms:
            t = datetime.fromtimestamp(t_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        else:
            t = None

        events.append({
            "section": "gdacs",  # يظهر في قسم الكوارث الطبيعية
            "title": f"🌍 زلزال داخل السعودية — قوة {mag:.1f} — {place}",
            "link": props.get("url"),
            "meta": {
                "magnitude": mag,
                "lat": lat,
                "lon": lon,
                "time": t,
                "source": "USGS",
            }
        })

    return events
