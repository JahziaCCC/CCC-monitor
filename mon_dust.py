# mon_dust.py
import os
import json
import datetime
import requests

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
STATE_FILE = "mon_dust_state.json"

# =========================
# مدن تمثيلية لجميع مناطق المملكة
# =========================
CITIES = [
    {"name":"الرياض","lat":24.7136,"lon":46.6753},
    {"name":"جدة","lat":21.5433,"lon":39.1728},
    {"name":"مكة","lat":21.3891,"lon":39.8579},
    {"name":"المدينة","lat":24.5247,"lon":39.5692},
    {"name":"الدمام","lat":26.4207,"lon":50.0888},
    {"name":"الأحساء","lat":25.3830,"lon":49.5860},
    {"name":"تبوك","lat":28.3838,"lon":36.5662},
    {"name":"حائل","lat":27.5114,"lon":41.7208},
    {"name":"القصيم","lat":26.3592,"lon":43.9818},
    {"name":"عرعر","lat":30.9753,"lon":41.0381},
    {"name":"سكاكا","lat":29.9697,"lon":40.2064},
    {"name":"جازان","lat":16.8892,"lon":42.5511},
    {"name":"أبها","lat":18.2465,"lon":42.5117},
    {"name":"نجران","lat":17.5650,"lon":44.2289},
    {"name":"الباحة","lat":20.0129,"lon":41.4677},
    {"name":"العلا","lat":26.6085,"lon":37.9232},
    {"name":"نيوم","lat":28.0000,"lon":35.0000},
]

AIR_API = "https://air-quality-api.open-meteo.com/v1/air-quality"

PM10_HIGH = 150
PM10_SEVERE = 250
INDEX_DIVISOR = 6.0


# =========================
# Telegram
# =========================
def tg_send_message(text):
    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    requests.post(url, json={
        "chat_id": CHAT_ID,
        "text": text,
        "disable_web_page_preview": True
    }, timeout=30).raise_for_status()


# =========================
# Helpers
# =========================
def now_ksa():
    return datetime.datetime.now(KSA_TZ).strftime("%Y-%m-%d %H:%M KSA")


def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def save_state(s):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


def level_icon(pm10):
    if pm10 >= PM10_SEVERE:
        return "🔴 شديد"
    if pm10 >= PM10_HIGH:
        return "🟠 مرتفع"
    return "🟢 طبيعي"


def trend_arrow(delta):
    if delta > 0:
        return "↑ يتصاعد"
    if delta < 0:
        return "↓ يتحسن"
    return "↔ مستقر"


def compute_index(max_pm10):
    return max(0, min(100, round(max_pm10 / INDEX_DIVISOR)))


# =========================
# Fetch PM10
# =========================
def fetch_pm10():
    lats = ",".join(str(c["lat"]) for c in CITIES)
    lons = ",".join(str(c["lon"]) for c in CITIES)

    r = requests.get(AIR_API, params={
        "latitude": lats,
        "longitude": lons,
        "timezone": "Asia/Riyadh",
        "current": "pm10"
    }, timeout=60)

    r.raise_for_status()
    data = r.json()

    results = []

    if isinstance(data, list):
        for city, item in zip(CITIES, data):
            pm10 = item.get("current", {}).get("pm10", 0)
            results.append({"name": city["name"], "pm10": float(pm10 or 0)})
    else:
        # fallback
        pm10 = data.get("current", {}).get("pm10", 0)
        for city in CITIES:
            results.append({"name": city["name"], "pm10": float(pm10 or 0)})

    return results


# =========================
# Build Report
# =========================
def build_report(now, dust_index, highest_level, top_city, top_value,
                 severe_list, high_list, trend):

    lines = []
    lines.append("🚨 تنبيه غبار – المملكة العربية السعودية")
    lines.append(f"🕒 {now}")
    lines.append("")
    lines.append(f"📌 أعلى مستوى مسجّل: {highest_level}")
    lines.append(f"📊 مؤشر الغبار: {dust_index}/100")
    lines.append(f"📈 اتجاه الحالة: {trend}")
    lines.append(f"📍 الأعلى: {top_city} ({int(top_value)} µg/m³)")
    lines.append("")
    lines.append("════════════════════")

    if severe_list:
        lines.append("🔴 شديد:")
        for n,v in severe_list:
            lines.append(f"• {n}: {int(v)} µg/m³")
        lines.append("")

    if high_list:
        lines.append("🟠 مرتفع:")
        for n,v in high_list:
            lines.append(f"• {n}: {int(v)} µg/m³")
        lines.append("")

    lines.append("")
    lines.append("✅ توصية تشغيلية سريعة:")
    lines.append("• رفع الجاهزية حسب الإجراءات الداخلية.")
    lines.append("• متابعة التحديث القادم حسب الجدولة.")

    return "\n".join(lines)


# =========================
# MAIN
# =========================
def main():
    now = now_ksa()

    readings = fetch_pm10()
    readings.sort(key=lambda x: x["pm10"], reverse=True)

    top = readings[0]
    max_pm10 = top["pm10"]

    dust_index = compute_index(max_pm10)
    highest_level = level_icon(max_pm10)

    severe_list = [(r["name"], r["pm10"]) for r in readings if r["pm10"] >= PM10_SEVERE]
    high_list = [(r["name"], r["pm10"]) for r in readings if PM10_HIGH <= r["pm10"] < PM10_SEVERE]

    state = load_state()
    prev = state.get("last_index", dust_index)
    delta = dust_index - prev
    trend = f"{trend_arrow(delta)} ({delta:+d})"

    state["last_index"] = dust_index
    save_state(state)

    report = build_report(
        now,
        dust_index,
        highest_level,
        top["name"],
        top["pm10"],
        severe_list,
        high_list,
        trend
    )

    tg_send_message(report)


if __name__ == "__main__":
    main()
