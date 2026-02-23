import requests
from datetime import datetime, timedelta, timezone

from sa_polygon import SAUDI_POLYGON, point_in_polygon

# =====================================
# إعدادات
# =====================================

MIN_MAG = 3.0
LOOKBACK_HOURS = 24

# كلمات استبعاد إضافية (فلتر أمان)
BLOCKED_COUNTRIES = [
    "iran",
    "iraq",
    "kuwait",
    "bahrain",
    "qatar",
    "oman",
    "yemen",
    "jordan",
    "egypt",
]

# =====================================
# جلب بيانات USGS
# =====================================

def fetch_usgs():

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=LOOKBACK_HOURS)

    url = "https://earthquake.usgs.gov/fdsnws/event/1/query"

    params = {
        "format": "geojson",
        "starttime": start_time.strftime("%Y-%m-%dT%H:%M:%S"),
        "endtime": end_time.strftime("%Y-%m-%dT%H:%M:%S"),
        "minmagnitude": MIN_MAG,
        "orderby": "time",
    }

    try:
        r = requests.get(url, params=params, timeout=25)
        r.raise_for_status()
        return r.json().get("features", [])

    except Exception:
        return []


# =====================================
# فلترة النص (أمان إضافي)
# =====================================

def blocked_place(place):

    p = place.lower()

    for c in BLOCKED_COUNTRIES:
        if c in p:
            return True

    return False


# =====================================
# تحويل الأحداث
# =====================================

def fetch():

    events = []
    data = fetch_usgs()

    for q in data:

        props = q.get("properties", {})
        geom = q.get("geometry", {})

        coords = geom.get("coordinates", [])
        if len(coords) < 2:
            continue

        lon = float(coords[0])
        lat = float(coords[1])

        # ⭐ فلترة جغرافية حقيقية
        if not point_in_polygon(lat, lon, SAUDI_POLYGON):
            continue

        mag = props.get("mag")
        if mag is None:
            continue

        try:
            mag = float(mag)
        except:
            continue

        if mag < MIN_MAG:
            continue

        place = props.get("place", "داخل المملكة")

        # ⭐ فلتر أمان ضد الدول المجاورة
        if blocked_place(place):
            continue

        t_ms = props.get("time")
        if t_ms:
            t = datetime.fromtimestamp(
                t_ms / 1000,
                tz=timezone.utc
            ).strftime("%Y-%m-%d %H:%M UTC")
        else:
            t = None

        events.append({
            "section": "gdacs",
            "title": f"🌍 زلزال داخل السعودية — قوة {mag:.1f} — {place}",
            "link": props.get("url"),
            "meta": {
                "magnitude": mag,
                "lat": lat,
                "lon": lon,
                "time": t,
                "source": "USGS"
            }
        })

    return events
