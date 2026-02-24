# mon_dusty.py
import os
import json
import hashlib
import datetime
import requests

STATE_FILE = "mewa_state_dust.json"
KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))

BOT = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Open-Meteo Air Quality API (مجاني)
AQ_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

# قائمة مناطق/مدن المملكة (17 موقع – اللي عندك سابقاً)
LOCATIONS = [
    ("الرياض", 24.7136, 46.6753),
    ("مكة", 21.3891, 39.8579),
    ("المدينة", 24.5247, 39.5692),
    ("جدة", 21.4858, 39.1925),
    ("المنطقة الشرقية (الدمام)", 26.4207, 50.0888),
    ("القصيم (بريدة)", 26.3592, 43.9818),
    ("عسير (أبها)", 18.2164, 42.5053),
    ("جازان", 16.8892, 42.5706),
    ("نجران", 17.5650, 44.2289),
    ("الباحة", 20.0129, 41.4677),
    ("تبوك", 28.3838, 36.5662),
    ("الجوف (سكاكا)", 29.9697, 40.2064),
    ("حائل", 27.5114, 41.7208),
    ("الحدود الشمالية (عرعر)", 30.9753, 41.0381),
    ("القريات", 31.3316, 37.3428),
    ("العلا", 26.6085, 37.9232),
    ("نيوم", 29.0, 35.0),
]

def _now():
    return datetime.datetime.now(tz=KSA_TZ)

def _sha(txt):
    return hashlib.sha256(txt.encode("utf-8")).hexdigest()

def _load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def _tg_send(text):
    if not BOT or not CHAT_ID:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    r = requests.post(url, json={
        "chat_id": CHAT_ID,
        "text": text,
        "disable_web_page_preview": True
    }, timeout=45)
    r.raise_for_status()

def _pm10_status(pm10):
    # حدود تقريبية تشغيلية (تقدر تعدلها)
    if pm10 is None:
        return "غير متاح مؤقتاً"
    if pm10 >= 2000:
        return f"⚠️ غبار شديد جدًا — {pm10:.0f} µg/m³"
    if pm10 >= 400:
        return f"🌪️ مؤشر غبار مرتفع — {pm10:.0f} µg/m³"
    return f"✅ غبار ضمن الطبيعي — {pm10:.0f} µg/m³"

def fetch_pm10(lat, lon, timeout=25):
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "pm10",
        "timezone": "UTC"
    }
    r = requests.get(AQ_URL, params=params, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    vals = (data.get("hourly") or {}).get("pm10") or []
    if not vals:
        return None
    # آخر قراءة
    return vals[-1]

def build_report(lines, notes):
    now = _now()
    rid = now.strftime("RPT-DUST-%Y%m%d-%H%M%S")
    out = []
    out.append("🌪️ تقرير الغبار وجودة الهواء (PM10)")
    out.append(f"رقم التقرير: {rid}")
    out.append("الجهة المصدرة: نظام الرصد الآلي – مركز المتابعة")
    out.append("تصنيف التقرير: تشغيلي – للاستخدام الداخلي")
    out.append("")
    out.append(f"🕒 تاريخ ووقت التحديث: {now.astimezone(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    out.append("⏱️ آلية التحديث: تلقائي")
    out.append("")
    out.append("════════════════════")
    out.append("1️⃣ قراءات PM10 (المملكة)")
    out.extend(lines if lines else ["- لا يوجد"])
    out.append("")
    out.append("════════════════════")
    out.append("2️⃣ ملاحظات")
    if notes:
        for n in notes:
            out.append(f"• {n}")
    else:
        out.append("• لا يوجد")
    return "\n".join(out)

def run(only_if_new=True):
    lines = []
    notes = []

    failed = 0
    for name, lat, lon in LOCATIONS:
        try:
            pm10 = fetch_pm10(lat, lon)
            status = _pm10_status(pm10)
            if "غير متاح" in status:
                lines.append(f"- {name}: غير متاح مؤقتاً")
            else:
                lines.append(f"- {name}: {status}")
        except Exception:
            failed += 1
            lines.append(f"- {name}: غير متاح مؤقتاً")

    if failed:
        notes.append(f"ℹ️ ملاحظة: تعذر جلب قراءة PM10 لعدد {failed} مواقع (مؤقتاً).")

    report = build_report(lines, notes)

    st = _load_state()
    h = _sha(report)
    if only_if_new and st.get("last") == h:
        print("no changes")
        return report

    _tg_send(report)
    st["last"] = h
    _save_state(st)
    return report
