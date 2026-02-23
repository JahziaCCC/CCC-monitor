# mon_dust.py
import os
import requests

# ✅ 15 موقع (13 منطقة + نيوم + العلا) + القريات (ضمن الحدود الشمالية) + حائل
# ملاحظة: نستخدم مدينة/نقطة ممثلة للمنطقة
CITIES = [
    ("الرياض", 24.7136, 46.6753),
    ("مكة", 21.3891, 39.8579),
    ("المدينة", 24.5247, 39.5692),
    ("جدة", 21.4858, 39.1925),
    ("المنطقة الشرقية (الدمام)", 26.4207, 50.0888),
    ("القصيم (بريدة)", 26.3592, 43.9818),
    ("عسير (أبها)", 18.2465, 42.5117),
    ("جازان", 16.8892, 42.5706),
    ("نجران", 17.5656, 44.2289),
    ("الباحة", 20.0129, 41.4677),
    ("تبوك", 28.3835, 36.5662),
    ("الجوف (سكاكا)", 29.9697, 40.2064),
    ("حائل", 27.5114, 41.7208),
    ("الحدود الشمالية (عرعر)", 30.9753, 41.0381),
    ("القريات", 31.3319, 37.3428),
    ("العلا", 26.6085, 37.9232),
    ("نيوم", 28.1700, 35.2500),
]

# Open-Meteo (مجاني) - PM10
OPEN_METEO_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

# حد التنبيه
PM10_HIGH = float(os.environ.get("PM10_HIGH", "300"))  # تقدر تغيّرها من Secrets لو تبغى

def _get_pm10(lat, lon):
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "pm10",
        "timezone": "UTC",
        "past_days": 1
    }
    r = requests.get(OPEN_METEO_URL, params=params, timeout=25)
    r.raise_for_status()
    data = r.json()
    pm10 = data.get("hourly", {}).get("pm10", [])
    if not pm10:
        return None
    # آخر قراءة
    return pm10[-1]

def fetch():
    events = []
    for name, lat, lon in CITIES:
        try:
            val = _get_pm10(lat, lon)
            if val is None:
                continue

            # نص موحّد مثل تقاريرك
            if val >= PM10_HIGH:
                events.append({
                    "section": "dust",
                    "title": f"🌪️ مؤشر غبار مرتفع — {name}: {int(round(val))} µg/m³"
                })
            else:
                # لو تبغى تعرض كل المدن حتى لو منخفضة، قلّي وأفعّلها
                pass

        except Exception as e:
            events.append({
                "section": "dust",
                "title": f"⚠️ تعذر قراءة PM10 — {name}: {e}"
            })

    # ترتيب تنازلي حسب الرقم
    def _val(t):
        # استخراج رقم من العنوان
        import re
        m = re.findall(r"\d+", t)
        return int(m[-1]) if m else 0

    events.sort(key=lambda x: _val(x.get("title", "")), reverse=True)
    return events
