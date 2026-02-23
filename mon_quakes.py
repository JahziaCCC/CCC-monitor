import requests
from datetime import datetime, timedelta, timezone

# =====================================
# حدود السعودية (تقريبية)
# =====================================

SAUDI_BBOX = {
    "min_lat": 16.0,
    "max_lat": 32.5,
    "min_lon": 34.0,
    "max_lon": 56.0,
}

MIN_MAG = 3.0

# =====================================
# جلب بيانات الزلازل من USGS
# =====================================

def fetch_usgs():

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=24)

    url = (
        "https://earthquake.usgs.gov/fdsnws/event/1/query"
        "?format=geojson"
        f"&starttime={start_time.strftime('%Y-%m-%d')}"
        f"&minmagnitude={MIN_MAG}"
    )

    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        return r.json().get("features", [])

    except Exception:
        return []


# =====================================
# فلترة داخل السعودية
# =====================================

def inside_saudi(lat, lon):
    return (
        SAUDI_BBOX["min_lat"] <= lat <= SAUDI_BBOX["max_lat"]
        and SAUDI_BBOX["min_lon"] <= lon <= SAUDI_BBOX["max_lon"]
    )


# =====================================
# تحويل الأحداث لصيغة النظام
# =====================================

def collect_quakes():

    events = []
    data = fetch_usgs()

    for q in data:

        props = q.get("properties", {})
        geom = q.get("geometry", {})

        coords = geom.get("coordinates", [])
        if len(coords) < 2:
            continue

        lon, lat = coords[0], coords[1]

        if not inside_saudi(lat, lon):
            continue

        mag = props.get("mag", 0)
        place = props.get("place", "داخل المملكة")

        if mag is None or mag < MIN_MAG:
            continue

        events.append({
            "section": "gdacs",   # نضعها مع الكوارث الطبيعية
            "title": f"🌍 زلزال داخل السعودية — قوة {mag:.1f} — {place}",
            "meta": {
                "magnitude": mag,
                "lat": lat,
                "lon": lon
            }
        })

    return events


# =====================================
# توافق مع main.py
# =====================================

def fetch():
    return collect_quakes()
