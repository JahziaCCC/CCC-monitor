import requests
from datetime import datetime, timedelta, timezone

# =====================================
# USGS Earthquake Catalog API (GeoJSON)
# https://earthquake.usgs.gov/fdsnws/event/1/
# =====================================

MIN_MAG_SA = 3.0

# حدود السعودية (Bounding Box تقريبية)
# يمكن تحسينها لاحقًا، لكنها ممتازة كبداية تشغيلية
SA_BBOX = {
    "minlatitude": 16.0,
    "maxlatitude": 32.5,
    "minlongitude": 34.0,
    "maxlongitude": 56.0,
}

LOOKBACK_HOURS = 24  # نبحث في آخر 24 ساعة


def _query_usgs():
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=LOOKBACK_HOURS)

    url = "https://earthquake.usgs.gov/fdsnws/event/1/query"
    params = {
        "format": "geojson",
        "starttime": start_time.strftime("%Y-%m-%dT%H:%M:%S"),
        "endtime": end_time.strftime("%Y-%m-%dT%H:%M:%S"),
        "minmagnitude": MIN_MAG_SA,
        **SA_BBOX,
        "orderby": "time",
    }

    try:
        r = requests.get(url, params=params, timeout=25)
        r.raise_for_status()
        data = r.json()
        return data.get("features", [])
    except Exception:
        return []


def fetch():
    """
    واجهة متوافقة مع main.py (لازم اسمها fetch)
    ترجع list من events بصيغة النظام
    """
    events = []
    features = _query_usgs()

    for f in features:
        props = f.get("properties", {})
        geom = f.get("geometry", {}) or {}
        coords = geom.get("coordinates", [])

        if len(coords) < 2:
            continue

        lon, lat = float(coords[0]), float(coords[1])
        mag = props.get("mag")
        place = props.get("place") or "داخل المملكة"

        if mag is None:
            continue

        try:
            mag = float(mag)
        except Exception:
            continue

        if mag < MIN_MAG_SA:
            continue

        # time بالميلي ثانية
        t_ms = props.get("time")
        if t_ms:
            t = datetime.fromtimestamp(t_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        else:
            t = None

        events.append({
            # نخليها ضمن الكوارث الطبيعية عشان تظهر في قسم GDACS عندك (3)
            "section": "gdacs",
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
