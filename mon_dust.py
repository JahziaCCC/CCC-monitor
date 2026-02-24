# mon_dust.py
import os
import datetime
import requests

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))

# Open-Meteo Air Quality API (لا يحتاج مفتاح)
AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

# 17 موقع (مناطق/مدن) — تقدر تزيد وتعدل
CITIES = {
    "الرياض": (24.7136, 46.6753),
    "مكة": (21.3891, 39.8579),
    "المدينة": (24.5247, 39.5692),
    "جدة": (21.5433, 39.1728),
    "المنطقة الشرقية (الدمام)": (26.4207, 50.0888),
    "القصيم (بريدة)": (26.3592, 43.9818),
    "عسير (أبها)": (18.2164, 42.5053),
    "جازان": (16.8892, 42.5706),
    "نجران": (17.5650, 44.2289),
    "الباحة": (20.0129, 41.4677),
    "تبوك": (28.3998, 36.5715),
    "الجوف (سكاكا)": (29.9697, 40.2064),
    "حائل": (27.5114, 41.7208),
    "الحدود الشمالية (عرعر)": (30.9753, 41.0381),
    "القريات": (31.3317, 37.3428),
    "العلا": (26.6085, 37.9232),
    "نيوم": (27.9678, 35.2137),
}

def _now_utc_iso():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def _classify(pm10_value: float) -> str:
    # تصنيف بسيط (تقدر تعدله)
    # طبيعي <= 250 ، مرتفع 251-600 ، شديد جدًا > 600
    if pm10_value is None:
        return "غير متاح مؤقتاً"
    if pm10_value <= 250:
        return f"✅ غبار ضمن الطبيعي — {pm10_value:.0f} µg/m³"
    if pm10_value <= 600:
        return f"🌪️ مؤشر غبار مرتفع — {pm10_value:.0f} µg/m³"
    return f"⚠️ غبار شديد جدًا — {pm10_value:.0f} µg/m³"

def fetch(timeout=25):
    """
    يرجع قائمة Events بصيغة المشروع:
    section='dust'
    title جاهز للعرض في التقرير
    meta فيها التفاصيل
    """
    events = []
    failed = 0

    for name, (lat, lon) in CITIES.items():
        try:
            params = {
                "latitude": lat,
                "longitude": lon,
                "hourly": "pm10",
                "timezone": "UTC",
                "past_days": 0,
            }
            r = requests.get(AIR_URL, params=params, timeout=timeout)
            r.raise_for_status()
            data = r.json()

            hourly = (data.get("hourly") or {})
            times = hourly.get("time") or []
            pm10s = hourly.get("pm10") or []

            pm10_value = None
            if times and pm10s:
                pm10_value = pm10s[-1]

            if pm10_value is None:
                failed += 1
                line = f"- {name}: غير متاح مؤقتاً"
            else:
                line = f"- {name}: {_classify(float(pm10_value))}".replace("—", "— " + name + ": ", 1)
                # النتيجة فوق تطلع مزدوجة، نخليها بسيطة:
                # "- الرياض: ⚠️ غبار شديد جدًا — 2652 µg/m³"
                # نبنيها يدويًا:
                cls = _classify(float(pm10_value))
                if cls == "غير متاح مؤقتاً":
                    line = f"- {name}: غير متاح مؤقتاً"
                else:
                    # cls: "⚠️ غبار شديد جدًا — 2652 µg/m³"
                    line = f"- {name}: {cls}"

            events.append({
                "section": "dust",
                "title": line.replace("- ", "").strip(),
                "meta": {
                    "city": name,
                    "pm10": pm10_value,
                    "lat": lat,
                    "lon": lon,
                    "ts": _now_utc_iso()
                }
            })
        except Exception as e:
            failed += 1
            events.append({
                "section": "dust",
                "title": f"{name}: غير متاح مؤقتاً",
                "meta": {
                    "city": name,
                    "error": str(e),
                    "lat": lat,
                    "lon": lon,
                    "ts": _now_utc_iso()
                }
            })

    # إضافة ملاحظة تشغيلية إذا فيه فشل
    if failed:
        events.append({
            "section": "other",
            "title": f"ℹ️ ملاحظة: تعذر جلب قراءة PM10 لعدد {failed} مواقع (مؤقتاً).",
            "meta": {"failed": failed, "ts": _now_utc_iso()}
        })

    return events
