import os
import json
import datetime
from typing import Dict, List, Optional, Tuple
import requests

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
STATE_FILE = "food_supply_state.json"

# TradingEconomics
TE_API_KEY = os.getenv("TE_API_KEY", "guest:guest")
TE_BASE = "https://api.tradingeconomics.com"

# =========================
# السلع (بعد الاستبعاد)
# =========================
COMMODITIES = [
    "القمح",
    "الأرز",
    "الذرة",
    "الشعير",
    "الزيت النباتي",
    "السكر",
    "حليب بودرة",
    "الأعلاف",
]

# كلمات مطابقة داخل Names في TradingEconomics (نطابق من قائمة commodities كاملة)
MATCH_KEYWORDS = {
    "القمح": ["wheat"],
    "الأرز": ["rice"],
    "الذرة": ["corn", "maize"],
    "الشعير": ["barley"],
    "الزيت النباتي": ["soybean oil", "palm oil", "rapeseed oil", "sunflower oil", "vegetable oil"],
    "السكر": ["sugar"],
    "حليب بودرة": ["milk", "skimmed milk powder", "whole milk powder", "milk powder", "dairy"],
    "الأعلاف": ["soybean meal", "feed", "corn", "wheat"],  # بدائل
}

# =========================
# تعرّض الموردين (Exposure)
# =========================
FLAGS = {
    "الهند": "🇮🇳",
    "باكستان": "🇵🇰",
    "مصر": "🇪🇬",
    "تركيا": "🇹🇷",
    "روسيا": "🇷🇺",
    "أوكرانيا": "🇺🇦",
    "إندونيسيا": "🇮🇩",
    "ماليزيا": "🇲🇾",
    "البرازيل": "🇧🇷",
    "نيوزيلندا": "🇳🇿",
}

EXPOSURE = {
    "القمح": ["روسيا", "أوكرانيا", "تركيا", "مصر"],
    "الذرة": ["أوكرانيا", "روسيا"],
    "الأرز": ["الهند", "باكستان"],
    "الشعير": ["روسيا", "أوكرانيا"],
    "الأعلاف": ["روسيا", "أوكرانيا"],
    "الزيت النباتي": ["إندونيسيا", "ماليزيا"],  # مهم جدًا للزيوت
    "السكر": ["البرازيل", "الهند"],             # مهم جدًا للسكر
    "حليب بودرة": ["نيوزيلندا"],                # مرجع قوي للألبان
}

# =========================
# أوزان المؤشر
# =========================
WEIGHTS = {
    "القمح": 0.22,
    "الأرز": 0.14,
    "الذرة": 0.14,
    "الشعير": 0.08,
    "الأعلاف": 0.10,
    "الزيت النباتي": 0.18,
    "السكر": 0.08,
    "حليب بودرة": 0.06,
}

# مستويات الخطر حسب WeeklyPercentualChange
THRESH_MED = 2.0   # >= 2% = 🟠
THRESH_HIGH = 5.0  # >= 5% = 🔴

# =========================
# Telegram
# =========================
def tg_send_message(text: str) -> None:
    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    requests.post(
        url,
        json={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True},
        timeout=30
    ).raise_for_status()

def now_ksa_str() -> str:
    return datetime.datetime.now(KSA_TZ).strftime("%Y-%m-%d %H:%M KSA")

# =========================
# State
# =========================
def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_state(s: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)

# =========================
# Helpers
# =========================
def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def level_from_weekly_change(pct: float) -> str:
    if pct >= THRESH_HIGH:
        return "🔴 مرتفع"
    if pct >= THRESH_MED:
        return "🟠 متوسط"
    return "🟢 طبيعي"

def trend_arrow(delta: int) -> str:
    if delta > 0:
        return "↑ يتصاعد"
    if delta < 0:
        return "↓ يتحسن"
    return "↔ مستقر"

def overall_level(idx: int) -> str:
    if idx >= 70:
        return "🔴 ضغط مرتفع"
    if idx >= 40:
        return "🟠 ضغط متوسط"
    return "🟢 طبيعي"

def format_exposure(names: List[str]) -> str:
    parts = []
    for n in names:
        parts.append(f"{FLAGS.get(n,'')} {n}".strip())
    return " | ".join(parts)

# =========================
# TradingEconomics
# =========================
def te_get_json(url: str) -> Optional[object]:
    try:
        r = requests.get(url, timeout=40)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def te_fetch_all_commodities() -> List[dict]:
    # هذا الـ endpoint يعيد قائمة commodities مع WeeklyPercentualChange عادة.  [oai_citation:1‡Trading Economics API](https://docs.tradingeconomics.com/markets/snapshot/?utm_source=chatgpt.com)
    url = f"{TE_BASE}/markets/commodities?c={TE_API_KEY}&f=json"
    data = te_get_json(url)
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    return []

def pick_best_match(items: List[dict], keywords: List[str]) -> Optional[dict]:
    """
    يختار أفضل عنصر commodity من القائمة بناءً على keywords في Name
    ويشترط وجود WeeklyPercentualChange
    """
    if not items:
        return None
    kws = [k.lower() for k in keywords]
    candidates = []
    for it in items:
        name = str(it.get("Name", "")).lower()
        if not name:
            continue
        if any(k in name for k in kws):
            w = it.get("WeeklyPercentualChange")
            if w is None:
                continue
            candidates.append(it)

    # لو وجدنا مرشحين، خذ الأقرب (الأقصر اسمًا عادة أكثر دقة)
    if candidates:
        candidates.sort(key=lambda x: len(str(x.get("Name", ""))))
        return candidates[0]

    return None

# =========================
# Unified index
# =========================
def compute_unified_index(per_item: Dict[str, Dict]) -> int:
    """
    تحويل تغير أسبوعي إلى مؤشر 0-100:
    0% => 0 ، 10% => 100 (قص)
    """
    score = 0.0
    total_w = 0.0
    for k, w in WEIGHTS.items():
        pct = per_item.get(k, {}).get("week_pct")
        if pct is None:
            continue
        item_score = clamp((pct / 10.0) * 100.0, 0.0, 100.0)
        score += w * item_score
        total_w += w
    if total_w == 0:
        return 0
    return int(round(clamp(score / total_w, 0, 100)))

# =========================
# Main
# =========================
def main():
    now = now_ksa_str()
    state = load_state()

    all_comms = te_fetch_all_commodities()

    per_item: Dict[str, Dict] = {}

    for item in COMMODITIES:
        kw = MATCH_KEYWORDS.get(item, [])
        found = pick_best_match(all_comms, kw)

        if not found:
            per_item[item] = {"week_pct": None, "level": "⚪ غير متاح"}
            continue

        try:
            week_pct = float(found.get("WeeklyPercentualChange"))
        except Exception:
            week_pct = None

        if week_pct is None:
            per_item[item] = {"week_pct": None, "level": "⚪ غير متاح"}
            continue

        prev_week = state.get("last_week_pct", {}).get(item, week_pct)
        delta = float(week_pct) - float(prev_week)

        per_item[item] = {
            "week_pct": float(week_pct),
            "level": level_from_weekly_change(float(week_pct)),
            "trend": f"{trend_arrow(1 if delta>0 else (-1 if delta<0 else 0))} ({delta:+.1f}%)",
            "src_name": found.get("Name"),
        }

    ranked = []
    for item, v in per_item.items():
        if v.get("week_pct") is None:
            continue
        ranked.append((item, float(v["week_pct"]), v.get("level", "")))
    ranked.sort(key=lambda x: x[1], reverse=True)

    unified = compute_unified_index(per_item)
    prev_unified = int(state.get("last_unified", unified))
    delta_unified = unified - prev_unified
    overall_tr = f"{trend_arrow(delta_unified)} ({delta_unified:+d})"
    overall_lvl = overall_level(unified)

    lines = []
    lines.append("🍞📦 رصد سلاسل إمداد الغذاء (B++ أسبوعي – Level 1) – المملكة العربية السعودية")
    lines.append(f"🕒 {now}")
    lines.append("")
    lines.append("════════════════════")
    lines.append("📊 الملخص التنفيذي")
    lines.append("")
    lines.append(f"📌 الحالة العامة: {overall_lvl}")
    lines.append(f"📈 مؤشر الأمن الغذائي: {unified}/100")
    lines.append(f"📊 اتجاه الحالة: {overall_tr}")
    lines.append("")
    lines.append("🏷️ أعلى السلع ضغطًا (7 أيام):")
    if ranked:
        for i, (name, pct, lvl) in enumerate(ranked[:3], start=1):
            lines.append(f"{i}️⃣ {name} — {lvl} {pct:+.1f}% (7d)")
    else:
        lines.append("• لا توجد بيانات أسبوعية كافية حالياً")
    lines.append("")
    lines.append("════════════════════")
    lines.append("📦 تفاصيل السلع (أسبوعي)")
    lines.append("")

    for item in COMMODITIES:
        v = per_item[item]
        pct = v.get("week_pct")
        lvl = v.get("level", "—")
        tr = v.get("trend", "—")
        exp = format_exposure(EXPOSURE.get(item, []))

        if pct is None:
            lines.append(f"• {item}: {lvl} | بيانات سعر غير متاحة حاليًا")
        else:
            lines.append(f"• {item}: {lvl} | {pct:+.1f}% (7d) | {tr}")

        if exp:
            lines.append(f"  دول التعرض: {exp}")

    lines.append("")
    lines.append("════════════════════")
    lines.append("🧭 توصية تشغيلية")
    if unified >= 70:
        lines.append("• تفعيل متابعة يومية مكثفة للحبوب والزيوت.")
        lines.append("• مراجعة المخزون التشغيلي وحدود إعادة الطلب.")
        lines.append("• تجهيز موردين بديلين ومسارات توريد بديلة.")
    elif unified >= 40:
        lines.append("• متابعة شبه يومية للحبوب والزيوت.")
        lines.append("• مراجعة المخزون للسلع الأعلى ضغطاً.")
    else:
        lines.append("• استمرار الرصد الأسبوعي حسب الجدولة.")
        lines.append("• رفع التنبيه عند تغيرات ≥ +5% خلال 7 أيام.")

    tg_send_message("\n".join(lines))

    # حفظ الحالة
    state["last_unified"] = unified
    state.setdefault("last_week_pct", {})
    for item in COMMODITIES:
        if per_item[item].get("week_pct") is not None:
            state["last_week_pct"][item] = per_item[item]["week_pct"]
    state["last_update"] = now
    save_state(state)

if __name__ == "__main__":
    main()
