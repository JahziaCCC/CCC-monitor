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
# Summary times (KSA)
# =========================
SUMMARY_HOURS = {6, 18}

# =========================
# Alert tuning
# =========================
DELTA_PM10_ALERT = 50.0  # لا يرسل تنبيه إلا إذا زادت أسوأ قيمة بهذا المقدار أو أكثر

# =========================
# KSA coverage (regions) + AlUla + NEOM
# =========================
KSA_POINTS: Dict[str, Tuple[float, float]] = {

    # المنطقة الوسطى
    "الرياض": (24.7136, 46.6753),
    "القصيم": (26.3260, 43.9750),
    "حائل": (27.5114, 41.7208),

    # المنطقة الغربية
    "جدة": (21.4858, 39.1925),
    "مكة": (21.3891, 39.8579),
    "المدينة": (24.5247, 39.5692),
    "العلا": (26.6085, 37.9222),

    # منطقة نيوم + تبوك
    "نيوم": (28.1050, 35.1040),
    "تبوك": (28.3838, 36.5662),

    # المنطقة الشرقية
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
def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "last_worst_level": None,      # e.g. "🟡 متوسط"
        "last_summary_key": None,      # e.g. "2026-02-25-06"
        "last_alert_key": None,        # avoid repeats
        "last_alert_worst_pm10": None, # last worst pm10 used in an alert
        "last_severe_set": [],         # list[str] of severe cities at last alert
    }

def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def send_telegram(text: str) -> None:
    if not BOT or not CHAT_ID:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    r = requests.post(url, json={"chat_id": CHAT_ID, "text": text}, timeout=25)
    print("TELEGRAM status:", r.status_code)
    print("TELEGRAM response:", r.text)
    r.raise_for_status()

def pm10_to_level(pm10: float) -> str:
    # Thresholds (µg/m³) - تشغيلية تقريبية للغبار
    if pm10 < 50:
        return "🟢 منخفض"
    if pm10 < 150:
        return "🟡 متوسط"
    if pm10 < 250:
        return "🟠 مرتفع"
    return "🔴 شديد"

def level_rank(level: str) -> int:
    return {"🟢 منخفض": 0, "🟡 متوسط": 1, "🟠 مرتفع": 2, "🔴 شديد": 3}.get(level, 0)

def compute_score(pm10_max: float) -> int:
    # 0..100 where 600 maps to 100 (أهدى من 300)
    return int(max(0, min(100, (pm10_max / 600.0) * 100)))

def fetch_pm10(lat: float, lon: float) -> Optional[float]:
    """
    Robust PM10:
    - Take latest 3 non-null values
    - Filter outliers (0 < PM10 < 600)
    - Return average of up to 3 values
    """
    url = (
        "https://air-quality-api.open-meteo.com/v1/air-quality"
        f"?latitude={lat}&longitude={lon}"
        "&hourly=pm10"
        "&timezone=Asia%2FRiyadh"
    )
    r = requests.get(url, timeout=25)
    r.raise_for_status()
    data = r.json()

    hourly = data.get("hourly", {})
    pm10s = hourly.get("pm10", [])
    if not pm10s:
        return None

    values: List[float] = []
    for v in reversed(pm10s):
        if v is None:
            continue
        try:
            fv = float(v)
        except Exception:
            continue
        if 0 < fv < 600:
            values.append(fv)
        if len(values) == 3:
            break

    if not values:
        return None

    return sum(values) / len(values)

def group_cities_by_level(city_values: Dict[str, float]) -> Dict[str, List[Tuple[str, float]]]:
    groups = {"🔴 شديد": [], "🟠 مرتفع": [], "🟡 متوسط": [], "🟢 منخفض": []}
    for city, v in city_values.items():
        groups[pm10_to_level(v)].append((city, v))
    for k in groups:
        groups[k].sort(key=lambda x: x[1], reverse=True)
    return groups

def format_group(title: str, items: List[Tuple[str, float]], max_lines: int = 10) -> str:
    if not items:
        return f"{title}\n- لا يوجد\n"
    lines = [f"{title}"]
    for city, v in items[:max_lines]:
        lines.append(f"• {city}: {v:.0f} µg/m³")
    if len(items) > max_lines:
        lines.append(f"… +{len(items)-max_lines} مناطق أخرى")
    return "\n".join(lines) + "\n"

def pin_important(city_values: Dict[str, float]) -> str:
    # دائما أظهر العلا ونيوم إن توفرت بياناتهم
    parts = []
    for name in ["العلا", "نيوم"]:
        if name in city_values:
            v = city_values[name]
            parts.append(f"• {name}: {v:.0f} µg/m³ ({pm10_to_level(v)})")
        else:
            parts.append(f"• {name}: لا توجد بيانات")
    return "\n".join(parts)

def build_summary(city_values: Dict[str, float], worst_city: str, worst_pm10: float) -> str:
    ts = now.strftime("%Y-%m-%d %H:%M")
    worst_level = pm10_to_level(worst_pm10)
    score = compute_score(worst_pm10)
    groups = group_cities_by_level(city_values)

    return (
        "🌪️ تقرير الغبار – المملكة العربية السعودية\n"
        f"🕒 تاريخ ووقت التحديث: {ts} KSA\n\n"
        "════════════════════\n"
        f"📊 مؤشر الغبار (0-100): {score}/100\n"
        f"📌 أعلى مستوى مسجّل: {worst_level}\n"
        f"📍 الأعلى تسجيلًا: {worst_city} ({worst_pm10:.0f} µg/m³)\n\n"
        "📍 مواقع مهمة:\n"
        f"{pin_important(city_values)}\n\n"
        "════════════════════\n"
        "📌 توزيع الحالة حسب المناطق (PM10):\n"
        f"{format_group('🔴 شديد:', groups['🔴 شديد'])}"
        f"{format_group('🟠 مرتفع:', groups['🟠 مرتفع'])}"
        f"{format_group('🟡 متوسط:', groups['🟡 متوسط'])}"
        f"{format_group('🟢 منخفض:', groups['🟢 منخفض'])}\n"
        "🧾 تفسير تشغيلي:\n"
        "• يعتمد القياس على PM10 كمؤشر تشغيلي للغبار.\n"
        "• تم تطبيق فلترة للقيم الشاذة وأخذ متوسط آخر 3 ساعات.\n"
        "• التنبيه فوري عند تغيّر جوهري (ارتفاع المستوى/زيادة كبيرة/تغير مناطق الشدة).\n"
    )

def build_alert(city_values: Dict[str, float], worst_city: str, worst_pm10: float) -> str:
    ts = now.strftime("%Y-%m-%d %H:%M")
    worst_level = pm10_to_level(worst_pm10)
    score = compute_score(worst_pm10)
    groups = group_cities_by_level(city_values)

    severe_txt = format_group("🔴 شديد:", groups["🔴 شديد"], max_lines=10)
    high_txt = format_group("🟠 مرتفع:", groups["🟠 مرتفع"], max_lines=10)

    return (
        "🚨 تنبيه غبار – المملكة العربية السعودية\n"
        f"🕒 {ts} KSA\n\n"
        f"📌 أعلى مستوى مسجّل: {worst_level}\n"
        f"📊 مؤشر الغبار: {score}/100\n"
        f"📍 الأعلى: {worst_city} ({worst_pm10:.0f} µg/m³)\n\n"
        "📍 مواقع مهمة:\n"
        f"{pin_important(city_values)}\n\n"
        "════════════════════\n"
        f"{severe_txt}"
        f"{high_txt}\n"
        "✅ توصية تشغيلية سريعة:\n"
        "• رفع الجاهزية حسب الإجراءات الداخلية.\n"
        "• متابعة التحديث القادم حسب الجدولة.\n"
    )

# =========================
# Main
# =========================
if __name__ == "__main__":
    print("Running Dust Report (Smart + Robust + Less Spam) ...")

    state = load_state()

    # Fetch values
    city_values: Dict[str, float] = {}
    for city, (lat, lon) in KSA_POINTS.items():
        try:
            v = fetch_pm10(lat, lon)
            if v is not None:
                city_values[city] = v
        except Exception as e:
            print(f"Fetch failed for {city}: {e}")

    # No data -> only summary times minimal message
    if not city_values:
        summary_key = f"{now.strftime('%Y-%m-%d')}-{now.hour:02d}"
        if now.hour in SUMMARY_HOURS and state.get("last_summary_key") != summary_key:
            msg = (
                "🌪️ تقرير الغبار – المملكة العربية السعودية\n"
                f"🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA\n\n"
                "⚠️ لم تتوفر بيانات PM10 كافية في هذه الدورة.\n"
            )
            send_telegram(msg)
            state["last_summary_key"] = summary_key
            save_state(state)
        print("No data; done.")
        raise SystemExit(0)

    # Worst point
    worst_city = max(city_values, key=lambda c: city_values[c])
    worst_pm10 = float(city_values[worst_city])
    worst_level = pm10_to_level(worst_pm10)

    # Severe set (cities that are severe now)
    groups = group_cities_by_level(city_values)
    severe_set_now: Set[str] = set([c for c, _ in groups["🔴 شديد"]])

    # Any high/severe anywhere?
    any_high_or_severe = any(level_rank(pm10_to_level(v)) >= 2 for v in city_values.values())

    # Alert logic (A) with anti-spam:
    last_worst_level = state.get("last_worst_level")
    last_alert_worst_pm10 = state.get("last_alert_worst_pm10")
    last_severe_set = set(state.get("last_severe_set", []) or [])

    # Unique key (still used as a guard)
    alert_key = f"{now.strftime('%Y-%m-%d')}-{now.hour:02d}-{worst_level}-{worst_city}-{int(worst_pm10)}"

    should_alert = False

    # 1) first run: alert only if high/severe exists
    if last_worst_level is None:
        should_alert = any_high_or_severe
    else:
        # 2) alert if worst level increased (e.g., متوسط -> مرتفع/شديد)
        if level_rank(worst_level) > level_rank(last_worst_level):
            should_alert = True

        # 3) alert if worst PM10 increased by >= DELTA_PM10_ALERT vs last alert
        if last_alert_worst_pm10 is not None:
            try:
                if (worst_pm10 - float(last_alert_worst_pm10)) >= DELTA_PM10_ALERT:
                    should_alert = True
            except Exception:
                pass

        # 4) alert if severe cities set changed (entered/exited)
        if severe_set_now != last_severe_set and any_high_or_severe:
            should_alert = True

    # extra guard: do not repeat same alert key
    if should_alert and state.get("last_alert_key") != alert_key:
        send_telegram(build_alert(city_values, worst_city, worst_pm10))
        state["last_alert_key"] = alert_key
        state["last_alert_worst_pm10"] = worst_pm10
        state["last_severe_set"] = sorted(list(severe_set_now))

    # Summary logic (B) only at 6 & 18, avoid duplicates
    summary_key = f"{now.strftime('%Y-%m-%d')}-{now.hour:02d}"
    if now.hour in SUMMARY_HOURS and state.get("last_summary_key") != summary_key:
        send_telegram(build_summary(city_values, worst_city, worst_pm10))
        state["last_summary_key"] = summary_key

    # Save state
    state["last_worst_level"] = worst_level
    save_state(state)

    print("Dust monitoring completed.")
