# mon_dust.py
import os
import time
import requests

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

PM10_HIGH = float(os.environ.get("PM10_HIGH", "300"))
PM10_VERY_HIGH = float(os.environ.get("PM10_VERY_HIGH", "1500"))

REQ_TIMEOUT = int(os.environ.get("DUST_TIMEOUT", "40"))
RETRIES = int(os.environ.get("DUST_RETRIES", "3"))
SLEEP_BETWEEN = float(os.environ.get("DUST_SLEEP", "1.2"))

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
            time.sleep(0.8 * (i + 1))
    raise last_err

def fetch():
    pm10_lines = []   # ✅ كل المدن (حتى لو طبيعي)
    dust_events = []  # ✅ فقط لاحتساب المخاطر/أبرز حدث
    failed_names = []
    ok = 0

    for name, lat, lon in CITIES:
        try:
            val = _request_pm10(lat, lon)
            if val is None:
                failed_names.append(name)
                pm10_lines.append(f"- {name}: غير متاح مؤقتاً")
            else:
                ok += 1
                v = int(round(val))

                # سطر عرض PM10 لكل المدن
                if v >= PM10_VERY_HIGH:
                    pm10_lines.append(f"- ⚠️ غبار شديد جدًا — {name}: {v} µg/m³")
                elif v >= PM10_HIGH:
                    pm10_lines.append(f"- 🌪️ مؤشر غبار مرتفع — {name}: {v} µg/m³")
                else:
                    pm10_lines.append(f"- ✅ غبار ضمن الطبيعي — {name}: {v} µg/m³")

                # أحداث “الغبار” فقط إذا مرتفع/شديد (للمخاطر/الملخص)
                if v >= PM10_HIGH:
                    title = f"🌪️ مؤشر غبار مرتفع — {name}: {v} µg/m³"
                    if v >= PM10_VERY_HIGH:
                        title = f"⚠️ غبار شديد جدًا — {name}: {v} µg/m³"
                    dust_events.append({
                        "section": "dust",
                        "title": title,
                        "value": v
                    })

        except Exception:
            failed_names.append(name)
            pm10_lines.append(f"- {name}: غير متاح مؤقتاً")

        time.sleep(SLEEP_BETWEEN)

    # ترتيب أحداث الغبار تنازليًا
    dust_events.sort(key=lambda x: int(x.get("value", 0)), reverse=True)

    events = dust_events[:]

    # ✅ أرسل قائمة PM10 كاملة تحت قسم مستقل
    events.append({
        "section": "pm10_list",
        "pm10_lines": pm10_lines
    })

    # ✅ أرسل ملاحظة تشغيلية (لن تكون “أبرز حدث”)
    if failed_names:
        events.append({
            "section": "ops_note",
            "title": f"ℹ️ ملاحظة: تعذر جلب قراءة PM10 لعدد {len(failed_names)} مواقع (مؤقتاً)."
        })

    return events
