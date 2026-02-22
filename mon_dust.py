import requests

# =====================================
# المدن المعتمدة للرصد (13 مدينة)
# =====================================

CITIES = [
    # الوسطى
    {"name": "الرياض", "lat": 24.7136, "lon": 46.6753},
    {"name": "القصيم", "lat": 26.3260, "lon": 43.9750},

    # الغربية
    {"name": "جدة", "lat": 21.5433, "lon": 39.1728},
    {"name": "مكة", "lat": 21.3891, "lon": 39.8579},
    {"name": "المدينة", "lat": 24.5247, "lon": 39.5692},
    {"name": "العلا", "lat": 26.6084, "lon": 37.9230},

    # الشمالية
    {"name": "تبوك", "lat": 28.3998, "lon": 36.5715},
    {"name": "نيوم", "lat": 28.1055, "lon": 35.0210},
    {"name": "القريات", "lat": 31.3318, "lon": 37.3428},

    # الشرقية
    {"name": "الدمام", "lat": 26.4207, "lon": 50.0888},
    {"name": "الأحساء", "lat": 25.3838, "lon": 49.5861},

    # الجنوبية
    {"name": "أبها", "lat": 18.2465, "lon": 42.5117},
    {"name": "جازان", "lat": 16.8892, "lon": 42.5511},
]

# =====================================
# جلب بيانات PM10 من Open-Meteo
# =====================================

def fetch_pm10(lat, lon):
    url = (
        "https://air-quality-api.open-meteo.com/v1/air-quality"
        f"?latitude={lat}&longitude={lon}"
        "&hourly=pm10"
    )

    try:
        r = requests.get(url, timeout=20)
        data = r.json()

        values = data.get("hourly", {}).get("pm10", [])
        values = [v for v in values if v is not None]

        if not values:
            return None

        return max(values[-6:])  # آخر 6 ساعات

    except Exception:
        return None


# =====================================
# إنشاء الأحداث للتقرير
# =====================================

def collect_dust_events():

    events = []

    for city in CITIES:

        pm10 = fetch_pm10(city["lat"], city["lon"])

        if pm10 is None:
            continue

        # فقط القيم المرتفعة تظهر في التقرير
        if pm10 >= 300:
            events.append({
                "section": "dust",
                "title": f"🌪️ مؤشر غبار مرتفع — {city['name']}: {int(pm10)} µg/m³",
                "meta": {
                    "city": city["name"],
                    "pm10": pm10,
                    "max_pm10": pm10
                }
            })

    return events
