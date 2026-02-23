# mon_dust.py
import os
import time
import requests
import re

# ✅ نقاط تمثيلية (15) — عدّلها كما تريد
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

OPEN_METEO_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

PM10_HIGH = float(os.environ.get("PM10_HIGH", "300"))         # حد “مرتفع”
PM10_VERY_HIGH = float(os.environ.get("PM10_VERY_HIGH", "1500"))  # “شديد جداً” للتنبيه

# إعدادات مقاومة التعطل
REQ_TIMEOUT = int(os.environ.get("DUST_TIMEOUT", "40"))   # 40s بدل 25
RETRIES = int(os.environ.get("DUST_RETRIES", "3"))        # إعادة المحاولة
SLEEP_BETWEEN = float(os.environ.get("DUST_SLEEP", "1.2"))# تهدئة بسيطة بين المدن

def _request_pm10(lat, lon):
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "pm10",
        "timezone": "UTC",
        "past_days": 1
    }

    last_err = None
    for i in range(RETRIES):
        try:
            r = requests.get(OPEN_METEO_URL, params=params, timeout=REQ_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            pm10 = data.get("hourly", {}).get("pm10", [])
            if not pm10:
                return None
            return pm10[-1]
        except Exception as e:
            last_err = e
            # backoff بسيط
            time.sleep(0.8 * (i + 1))

    # بعد كل المحاولات
    raise last_err

def fetch():
    events = []
    failed = []

    for name, lat, lon in CITIES:
        try:
            val = _request_pm10(lat, lon)

            if val is None:
                failed.append(name)
            else:
                v = int(round(val))
                if v >= PM10_HIGH:
                    events.append({
                        "section": "dust",
                        "title": f"🌪️ مؤشر غبار مرتفع — {name}: {v} µg/m³",
                        "value": v
                    })
        except Exception:
            failed.append(name)

        time.sleep(SLEEP_BETWEEN)

    # ترتيب تنازلي
    events.sort(key=lambda x: int(x.get("value", 0)), reverse=True)

    # ✅ لا نطبع أخطاء داخل التقرير (بدون تشويش)
    # لو فشلت مدن، نضيف ملاحظة واحدة مختصرة “غير مؤثرة”
    if failed:
        events.append({
            "section": "dust",
            "title": f"ℹ️ ملاحظة: تعذر جلب قراءة PM10 لعدد {len(failed)} مواقع (مؤقتاً).",
            "value": -1
        })

    # لو ما فيه أي غبار مرتفع
    if not any(e.get("value", 0) >= PM10_HIGH for e in events):
        return []

    return events
