# mon_food_supply.py
import os
import json
import datetime
from typing import Dict, List, Optional, Tuple

import requests

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
STATE_FILE = "food_supply_state.json"

# Trading Economics (يدعم weekly change جاهز)
# docs: /markets/commodities و /markets/search/{term} مع category=commodity
# https://api.tradingeconomics.com/markets/commodities?c=API_KEY
# https://api.tradingeconomics.com/markets/search/wheat?c=API_KEY&category=commodity&f=json
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

# مصطلحات البحث داخل TradingEconomics لكل سلعة
# (نجرّب أكثر من term ونأخذ أول نتيجة "Name" مناسبة)
TE_TERMS = {
    "القمح": ["wheat"],
    "الأرز": ["rice"],
    "الذرة": ["corn"],
    "الشعير": ["barley"],
    "الزيت النباتي": ["soybean oil", "palm oil", "rapeseed oil"],
    "السكر": ["sugar"],
    "حليب بودرة": ["skim milk powder", "milk powder", "dairy"],
    "الأعلاف": ["soybean meal", "feed", "corn"],  # لو ما لقى feed نستخدم soybean meal أو corn كبديل
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
    "الزيت النباتي": ["إندونيسيا", "ماليزيا"],
    "السكر": ["البرازيل", "الهند"],
    "حليب بودرة": ["نيوزيلندا"],
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
# TradingEconomics fetch
# =========================
def te_get_json(url: str) -> Optional[dict]:
    try:
        r = requests.get(url, timeout=40)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def te_search_best(term: str) -> Optional[dict]:
    """
    يبحث في TE ويعيد أفضل نتيجة commodity لها WeeklyPercentualChange
    """
    t = term.replace(" ", "%20")
    url = f"{TE_BASE}/markets/search/{t}?c={TE_API_KEY}&category=commodity&f=json"
    data = te_get_json(url)
    if not data or not isinstance(data, list):
        return None

    # خذ أول عنصر عنده Name و WeeklyPercentualChange (أغلب الوقت هو المطلوب)
    for item in data:
        if not isinstance(item, dict):
            continue
        if item.get("Type") not in (None, "", "commodity"):
            # بعض الردود ما تعطي Type بشكل ثابت، فنتساهل
            pass
        if item.get("Name") and (item.get("WeeklyPercentualChange") is not None):
            return item

    # fallback: أول عنصر حتى لو ما فيه weekly (نحاول لاحقاً)
    for item in data:
        if isinstance(item, dict) and item.get("Name"):
            return item

    return None

def te_pick_commodity(ar_item: str) -> Tuple[Optional[float], Optional[str], Optional[str]]:
    """
    يرجع (weekly_pct, name, url)
    """
    terms = TE_TERMS.get(ar_item, [])
    for term in terms:
        found = te_search_best(term)
        if not found:
            continue
        w = found.get("WeeklyPercentualChange")
        name = found.get("Name")
        url = found.get("URL")
        if w is None:
            continue
        try:
            return float(w), str(name), str(url)
        except Exception:
            continue
    return None, None, None

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

    per_item: Dict[str, Dict] = {}

    # جلب weekly change لكل سلعة من TE
    for item in COMMODITIES:
        week_pct, te_name, te_url = te_pick_commodity(item)

        if week_pct is None:
            per_item[item] = {
                "week_pct": None,
                "level": "⚪ غير متاح",
                "source": "TE",
                "name": te_name,
                "url": te_url,
            }
        else:
            prev_week = state.get("last_week_pct", {}).get(item, week_pct)
            delta = float(week_pct) - float(prev_week)

            per_item[item] = {
                "week_pct": float(week_pct),
                "level": level_from_weekly_change(float(week_pct)),
                "source": "TE",
                "name": te_name,
                "url": te_url,
                "trend": f"{trend_arrow(1 if delta>0 else (-1 if delta<0 else 0))} ({delta:+.1f}%)",
            }

    # أعلى 3 ضغطًا
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

    # بناء التقرير
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

    report = "\n".join(lines)
    tg_send_message(report)

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
