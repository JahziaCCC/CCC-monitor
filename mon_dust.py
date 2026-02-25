import os
import json
import datetime
import requests
from typing import Dict, Tuple, List

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
# Settings
# =========================
STATE_FILE = "dust_state.json"
SUMMARY_HOURS = {6, 18}
DELTA_PM10_ALERT = 80.0
API_TIMEOUT_SEC = 20
API_RETRIES = 2

# =========================
# Locations (Saudi Arabia)
# =========================
KSA_POINTS: Dict[str, Tuple[float, float]] = {

    "الرياض": (24.7136, 46.6753),
    "القصيم": (26.3260, 43.9750),
    "حائل": (27.5114, 41.7208),

    "جدة": (21.4858, 39.1925),
    "مكة": (21.3891, 39.8579),
    "المدينة": (24.5247, 39.5692),
    "العلا": (26.6085, 37.9222),

    "نيوم": (28.1050, 35.1040),
    "تبوك": (28.3838, 36.5662),

    "الدمام": (26.4207, 50.0888),
    "الأحساء": (25.3833, 49.5833),
    "الجبيل": (27.0174, 49.6225),

    "أبها": (18.2465, 42.5117),
    "جازان": (16.8892, 42.5511),
    "نجران": (17.5650, 44.2289),
    "الباحة": (20.0129, 41.4677),

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
        except:
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
    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    r = requests.post(url, json={"chat_id": CHAT_ID, "text": text}, timeout=25)
    r.raise_for_status()

def pm10_to_level(v):
    if v < 50: return "🟢 منخفض"
    if v < 150: return "🟡 متوسط"
    if v < 250: return "🟠 مرتفع"
    return "🔴 شديد"

def level_rank(level):
    return {"🟢 منخفض":0,"🟡 متوسط":1,"🟠 مرتفع":2,"🔴 شديد":3}[level]

def compute_score(v):
    return int(max(0, min(100, (v/600)*100)))

def fetch_pm10(lat, lon):
    url = (
        "https://air-quality-api.open-meteo.com/v1/air-quality"
        f"?latitude={lat}&longitude={lon}"
        "&hourly=pm10&timezone=Asia%2FRiyadh"
    )

    for _ in range(API_RETRIES):
        try:
            r = requests.get(url, timeout=API_TIMEOUT_SEC)
            r.raise_for_status()
            data = r.json()
            pm10s = data.get("hourly", {}).get("pm10", [])

            vals=[]
            for x in reversed(pm10s):
                if x and 0 < x < 600:
                    vals.append(float(x))
                if len(vals)==3:
                    break

            if not vals:
                return None

            return sum(vals)/len(vals)

        except Exception:
            continue

    return None

def group_levels(values):
    g={"🔴 شديد":[],"🟠 مرتفع":[],"🟡 متوسط":[],"🟢 منخفض":[]}
    for c,v in values.items():
        g[pm10_to_level(v)].append((c,v))
    for k in g:
        g[k].sort(key=lambda x:x[1], reverse=True)
    return g

def format_group(title, items):
    if not items:
        return f"{title}\n- لا يوجد\n"
    txt=[title]
    for c,v in items[:10]:
        txt.append(f"• {c}: {v:.0f} µg/m³")
    return "\n".join(txt)+"\n"

# =========================
# Important sites (show only if data exists)
# =========================
def pin_sites(values):
    out=[]

    if "العلا" in values:
        v=values["العلا"]
        out.append(f"• العلا: {v:.0f} µg/m³ ({pm10_to_level(v)})")

    if "نيوم" in values:
        v=values["نيوم"]
        out.append(f"• نيوم: {v:.0f} µg/m³ ({pm10_to_level(v)})")

    if not out:
        return ""

    return "\n".join(out)

# =========================
# Reports
# =========================
def build_summary(values,worst_city,worst):
    score=compute_score(worst)
    lvl=pm10_to_level(worst)
    g=group_levels(values)

    important_sites = pin_sites(values)
    important_section = f"\n📍 مواقع مهمة:\n{important_sites}\n" if important_sites else ""

    return f"""🌪️ تقرير الغبار – المملكة العربية السعودية
🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA

════════════════════
📊 مؤشر الغبار: {score}/100
📌 أعلى مستوى: {lvl}
📍 الأعلى: {worst_city} ({worst:.0f} µg/m³){important_section}
════════════════════
{format_group('🔴 شديد:',g['🔴 شديد'])}
{format_group('🟠 مرتفع:',g['🟠 مرتفع'])}
{format_group('🟡 متوسط:',g['🟡 متوسط'])}
{format_group('🟢 منخفض:',g['🟢 منخفض'])}
"""

def build_alert(values,worst_city,worst):
    score=compute_score(worst)
    lvl=pm10_to_level(worst)
    g=group_levels(values)

    important_sites = pin_sites(values)
    important_section = f"\n📍 مواقع مهمة:\n{important_sites}\n" if important_sites else ""

    return f"""🚨 تنبيه غبار – المملكة العربية السعودية
🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA

📌 أعلى مستوى مسجّل: {lvl}
📊 مؤشر الغبار: {score}/100
📍 الأعلى: {worst_city} ({worst:.0f} µg/m³){important_section}
════════════════════
{format_group('🔴 شديد:',g['🔴 شديد'])}
{format_group('🟠 مرتفع:',g['🟠 مرتفع'])}

✅ توصية تشغيلية سريعة:
• رفع الجاهزية حسب الإجراءات الداخلية.
• متابعة التحديث القادم حسب الجدولة.
"""

# =========================
# Main
# =========================
if __name__=="__main__":

    state=load_state()
    values={}

    for c,(lat,lon) in KSA_POINTS.items():
        v=fetch_pm10(lat,lon)
        if v is not None:
            values[c]=v

    if not values:
        raise SystemExit("No data")

    worst_city=max(values,key=lambda x:values[x])
    worst=values[worst_city]
    worst_level=pm10_to_level(worst)

    groups=group_levels(values)
    severe_set=set([c for c,_ in groups["🔴 شديد"]])

    should_alert=False

    if state["last_worst_level"] is None:
        should_alert=len(severe_set)>0
    else:
        if level_rank(worst_level)>level_rank(state["last_worst_level"]):
            should_alert=True

        if state["last_alert_worst_pm10"]:
            if worst-state["last_alert_worst_pm10"]>=DELTA_PM10_ALERT:
                should_alert=True

        if set(state["last_severe_set"])!=severe_set:
            should_alert=True

    if should_alert:
        send_telegram(build_alert(values,worst_city,worst))
        state["last_alert_worst_pm10"]=worst
        state["last_severe_set"]=list(severe_set)

    summary_key=f"{now.strftime('%Y-%m-%d')}-{now.hour}"
    if now.hour in SUMMARY_HOURS and state["last_summary_key"]!=summary_key:
        send_telegram(build_summary(values,worst_city,worst))
        state["last_summary_key"]=summary_key

    state["last_worst_level"]=worst_level
    save_state(state)

    print("Dust monitoring completed.")
