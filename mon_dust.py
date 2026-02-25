import os
import json
import datetime
import requests
from typing import Dict, Tuple, Optional, List, Set

# =========================
# Telegram
# =========================
BOT = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

# =========================
# Time
# =========================
KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
now = datetime.datetime.now(KSA_TZ)

# =========================
# State
# =========================
STATE_FILE = "dust_state.json"

# =========================
# Settings
# =========================
SUMMARY_HOURS = {6, 18}
DELTA_PM10_ALERT = 80.0   # تقليل تكرار التنبيهات
API_TIMEOUT_SEC = 20
API_RETRIES = 2           # عدد المحاولات لكل مدينة

# =========================
# Locations (Saudi Arabia + AlUla + NEOM)
# =========================
KSA_POINTS: Dict[str, Tuple[float, float]] = {

    # الوسطى
    "الرياض": (24.7136, 46.6753),
    "القصيم": (26.3260, 43.9750),
    "حائل": (27.5114, 41.7208),

    # الغربية
    "جدة": (21.4858, 39.1925),
    "مكة": (21.3891, 39.8579),
    "المدينة": (24.5247, 39.5692),
    "العلا": (26.6085, 37.9222),

    # نيوم + تبوك
    "نيوم": (28.1050, 35.1040),
    "تبوك": (28.3838, 36.5662),

    # الشرقية
    "الدمام": (26.4207, 50.0888),
    "الأحساء": (25.3833, 49.5833),
    "الجبيل": (27.0174, 49.6225),

    # الجنوب
    "أبها": (18.2465, 42.5117),
    "جازان": (16.8892, 42.5511),
    "نجران": (17.5650, 44.2289),
    "الباحة": (20.0129, 41.4677),

    # الشمال
    "عرعر": (30.9753, 41.0381),
    "سكاكا": (29.9697, 40.2064),
    "القريات": (31.3318, 37.3428),
}

# =========================
# Helpers
# =========================
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "last_worst_level": None,
        "last_summary_key": None,
        "last_alert_worst_pm10": None,
        "last_severe_set": []
    }

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def send_telegram(text):
    if not BOT or not CHAT_ID:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    r = requests.post(url, json={"chat_id": CHAT_ID, "text": text}, timeout=25)
    print("TELEGRAM:", r.status_code)
    print("TELEGRAM response:", r.text)
    r.raise_for_status()

def pm10_to_level(v):
    if v < 50: return "🟢 منخفض"
    if v < 150: return "🟡 متوسط"
    if v < 250: return "🟠 مرتفع"
    return "🔴 شديد"

def level_rank(level):
    return {"🟢 منخفض": 0, "🟡 متوسط": 1, "🟠 مرتفع": 2, "🔴 شديد": 3}[level]

def compute_score(v):
    # 600 => 100
    return int(max(0, min(100, (v / 600.0) * 100)))

def fetch_pm10(lat, lon) -> Optional[float]:
    """
    Robust fetch:
    - retries
    - timeout-safe (no crash)
    - filters outliers (0 < PM10 < 600)
    - average of latest 3 values
    """
    url = (
        "https://air-quality-api.open-meteo.com/v1/air-quality"
        f"?latitude={lat}&longitude={lon}"
        "&hourly=pm10&timezone=Asia%2FRiyadh"
    )

    last_err = None
    for attempt in range(1, API_RETRIES + 1):
        try:
            r = requests.get(url, timeout=API_TIMEOUT_SEC)
            r.raise_for_status()
            data = r.json()
            pm10s = data.get("hourly", {}).get("pm10", [])

            vals = []
            for x in reversed(pm10s):
                if x is None:
                    continue
                try:
                    fx = float(x)
                except Exception:
                    continue
                if 0 < fx < 600:
                    vals.append(fx)
                if len(vals) == 3:
                    break

            if not vals:
                return None

            return sum(vals) / len(vals)

        except Exception as e:
            last_err = e
            print(f"API attempt {attempt}/{API_RETRIES} failed: {e}")

    print(f"API failed finally: {last_err}")
    return None

def group_levels(city_values):
    g = {"🔴 شديد": [], "🟠 مرتفع": [], "🟡 متوسط": [], "🟢 منخفض": []}
    for c, v in city_values.items():
        g[pm10_to_level(v)].append((c, v))
    for k in g:
        g[k].sort(key=lambda x: x[1], reverse=True)
    return g

def format_group(title, items, max_lines=10):
    if not items:
        return f"{title}\n- لا يوجد\n"
    txt = [title]
    for c, v in items[:max_lines]:
        txt.append(f"• {c}: {v:.0f} µg/m³")
    if len(items) > max_lines:
        txt.append(f"… +{len(items) - max_lines} مناطق أخرى")
    return "\n".join(txt) + "\n"

def pin_sites(values):
    out = []
    for n in ["العلا", "نيوم"]:
        if n in values:
            v = values[n]
            out.append(f"• {n}: {v:.0f} µg/m³ ({pm10_to_level(v)})")
        else:
            out.append(f"• {n}: لا توجد بيانات")
    return "\n".join(out)

# =========================
# Report builders
# =========================
def build_summary(values, worst_city, worst):
    score = compute_score(worst)
    lvl = pm10_to_level(worst)
    g = group_levels(values)

    return f"""🌪️ تقرير الغبار – المملكة العربية السعودية
🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA

════════════════════
📊 مؤشر الغبار: {score}/100
📌 أعلى مستوى: {lvl}
📍 الأعلى: {worst_city} ({worst:.0f} µg/m³)

📍 مواقع مهمة:
{pin_sites(values)}

════════════════════
{format_group('🔴 شديد:', g['🔴 شديد'])}
{format_group('🟠 مرتفع:', g['🟠 مرتفع'])}
{format_group('🟡 متوسط:', g['🟡 متوسط'])}
{format_group('🟢 منخفض:', g['🟢 منخفض'])}

🧾 تفسير تشغيلي:
• متوسط آخر 3 ساعات + فلترة القيم الشاذة.
• يتم إرسال تنبيه فوري عند تغير جوهري.
"""

def build_alert(values, worst_city, worst):
    score = compute_score(worst)
    lvl = pm10_to_level(worst)
    g = group_levels(values)

    return f"""🚨 تنبيه غبار – المملكة العربية السعودية
🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA

📌 أعلى مستوى مسجّل: {lvl}
📊 مؤشر الغبار: {score}/100
📍 الأعلى: {worst_city} ({worst:.0f} µg/m³)

📍 مواقع مهمة:
{pin_sites(values)}

════════════════════
{format_group('🔴 شديد:', g['🔴 شديد'])}
{format_group('🟠 مرتفع:', g['🟠 مرتفع'])}

✅ توصية تشغيلية سريعة:
• رفع الجاهزية حسب الإجراءات الداخلية.
• متابعة التحديث القادم حسب الجدولة.
"""

def build_no_data_message(failed_cities: List[str]) -> str:
    ts = now.strftime("%Y-%m-%d %H:%M")
    preview = "، ".join(failed_cities[:8])
    extra = f" … +{len(failed_cities)-8}" if len(failed_cities) > 8 else ""
    return (
        "🌪️ تقرير الغبار – المملكة العربية السعودية\n"
        f"🕒 {ts} KSA\n\n"
        "⚠️ تعذر جلب بيانات PM10 في هذه الدورة.\n"
        f"📍 المدن المتأثرة: {preview}{extra}\n"
        "✅ سيتم المحاولة تلقائيًا في الدورة القادمة.\n"
    )

# =========================
# Main
# =========================
if __name__ == "__main__":
    print("Running Dust Report (robust, no timeouts) ...")

    state = load_state()
    values: Dict[str, float] = {}
    failed: List[str] = []

    for c, (lat, lon) in KSA_POINTS.items():
        v = fetch_pm10(lat, lon)
        if v is not None:
            values[c] = v
        else:
            failed.append(c)

    # If no data at all: do NOT fail workflow; send status message at summary times only
    if not values:
        summary_key = f"{now.strftime('%Y-%m-%d')}-{now.hour:02d}"
        if now.hour in SUMMARY_HOURS and state.get("last_summary_key") != summary_key:
            send_telegram(build_no_data_message(failed))
            state["last_summary_key"] = summary_key
            save_state(state)
        print("No data available; exiting cleanly.")
        raise SystemExit(0)

    worst_city = max(values, key=lambda x: values[x])
    worst = values[worst_city]
    worst_level = pm10_to_level(worst)

    groups = group_levels(values)
    severe_set = set([c for c, _ in groups["🔴 شديد"]])
    any_high_or_severe = (len(groups["🔴 شديد"]) + len(groups["🟠 مرتفع"])) > 0

    should_alert = False

    if state.get("last_worst_level") is None:
        should_alert = any_high_or_severe
    else:
        if level_rank(worst_level) > level_rank(state["last_worst_level"]):
            should_alert = True

        last_alert_pm10 = state.get("last_alert_worst_pm10")
        if last_alert_pm10 is not None and (worst - float(last_alert_pm10)) >= DELTA_PM10_ALERT:
            should_alert = True

        if set(state.get("last_severe_set", [])) != severe_set and any_high_or_severe:
            should_alert = True

    # Send alert if needed
    if should_alert:
        send_telegram(build_alert(values, worst_city, worst))
        state["last_alert_worst_pm10"] = float(worst)
        state["last_severe_set"] = list(severe_set)

    # Summary at 6 & 18 only
    summary_key = f"{now.strftime('%Y-%m-%d')}-{now.hour:02d}"
    if now.hour in SUMMARY_HOURS and state.get("last_summary_key") != summary_key:
        send_telegram(build_summary(values, worst_city, worst))
        state["last_summary_key"] = summary_key

    state["last_worst_level"] = worst_level
    save_state(state)

    print("Dust monitoring completed.")
