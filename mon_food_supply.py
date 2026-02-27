import os
import json
import datetime
from typing import Dict, List, Optional, Tuple
import requests

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
STATE_FILE = "food_supply_state.json"

TE_API_KEY = os.getenv("TE_API_KEY", "guest:guest")
TE_BASE = "https://api.tradingeconomics.com"

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

# كلمات مطابقة (بنستخدمها في commodities + search fallback)
MATCH_KEYWORDS = {
    "القمح": ["wheat"],
    "الأرز": ["rice"],
    "الذرة": ["corn", "maize"],
    "الشعير": ["barley"],
    "الزيت النباتي": ["palm oil", "soybean oil", "rapeseed oil", "sunflower oil", "vegetable oil", "canola oil"],
    "السكر": ["sugar"],
    "حليب بودرة": ["milk powder", "skim milk powder", "whole milk powder", "milk", "dairy"],
    "الأعلاف": ["soybean meal", "feed", "corn", "wheat"],
}

# مصطلحات search (إذا commodities ما أعطى نتيجة)
SEARCH_TERMS = {
    "القمح": ["wheat", "chicago wheat", "kansas wheat"],
    "الأرز": ["rice", "rough rice", "thai rice"],
    "الذرة": ["corn", "maize"],
    "الشعير": ["barley"],
    "الزيت النباتي": ["palm oil", "soybean oil", "rapeseed oil", "sunflower oil", "vegetable oil"],
    "السكر": ["sugar", "raw sugar", "white sugar"],
    "حليب بودرة": ["skim milk powder", "whole milk powder", "milk powder", "dairy"],
    "الأعلاف": ["soybean meal", "feed", "corn"],
}

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

THRESH_MED = 2.0
THRESH_HIGH = 5.0

# ========== Telegram ==========
def tg_send_message(text: str) -> None:
    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    requests.post(
        url,
        json={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True},
        timeout=30
    ).raise_for_status()

def now_ksa_str() -> str:
    return datetime.datetime.now(KSA_TZ).strftime("%Y-%m-%d %H:%M KSA")

# ========== State ==========
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

# ========== Helpers ==========
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

# ========== TradingEconomics ==========
def te_get_json(url: str) -> Optional[object]:
    try:
        r = requests.get(url, timeout=45)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def te_fetch_all_commodities() -> List[dict]:
    url = f"{TE_BASE}/markets/commodities?c={TE_API_KEY}&f=json"
    data = te_get_json(url)
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    return []

def te_search(term: str) -> List[dict]:
    t = term.replace(" ", "%20")
    url = f"{TE_BASE}/markets/search/{t}?c={TE_API_KEY}&category=commodity&f=json"
    data = te_get_json(url)
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    return []

def pick_best_match_any(items: List[dict], keywords: List[str]) -> Optional[dict]:
    """
    يطابق على Name فقط (بدون اشتراط weekly) ثم نشتق weekly لاحقاً.
    """
    kws = [k.lower() for k in keywords]
    candidates = []
    for it in items:
        name = str(it.get("Name", "")).lower()
        if not name:
            continue
        if any(k in name for k in kws):
            candidates.append(it)

    if not candidates:
        return None

    # نفضّل الأقصر اسمًا (غالباً الأكثر مباشرة) ثم اللي عنده weekly إن وجد
    def score(it):
        name_len = len(str(it.get("Name", "")))
        has_weekly = 0 if it.get("WeeklyPercentualChange") is not None else 1
        return (has_weekly, name_len)

    candidates.sort(key=score)
    return candidates[0]

def extract_weekly_pct(it: dict) -> Tuple[Optional[float], str]:
    """
    يرجع (weekly_pct, mode)
    mode:
      - "weekly" إذا WeeklyPercentualChange موجود
      - "est_m" إذا مشتق من MonthlyPercentualChange/4.3
      - "est_d" إذا مشتق من DailyPercentualChange*5
      - "none" إذا ما قدرنا
    """
    w = it.get("WeeklyPercentualChange")
    if w is not None:
        try:
            return float(w), "weekly"
        except:
            pass

    m = it.get("MonthlyPercentualChange")
    if m is not None:
        try:
            # تقريب أسبوعي من شهري
            return float(m) / 4.3, "est_m"
        except:
            pass

    d = it.get("DailyPercentualChange")
    if d is not None:
        try:
            # تقريب أسبوعي من يومي
            return float(d) * 5.0, "est_d"
        except:
            pass

    return None, "none"

# ========== Unified index ==========
def compute_unified_index(per_item: Dict[str, Dict]) -> int:
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

# ========== Main ==========
def main():
    now = now_ksa_str()
    state = load_state()

    all_comms = te_fetch_all_commodities()

    per_item: Dict[str, Dict] = {}

    for item in COMMODITIES:
        kw = MATCH_KEYWORDS.get(item, [])
        found = pick_best_match_any(all_comms, kw)

        # إذا ما وجدنا في commodities → نستخدم search fallback
        if not found:
            for term in SEARCH_TERMS.get(item, []):
                results = te_search(term)
                found = pick_best_match_any(results, kw if kw else [term])
                if found:
                    break

        if not found:
            per_item[item] = {
                "week_pct": None,
                "level": "⚪ غير متاح",
                "src_name": None,
                "mode": "none",
                "reason": "لم يتم العثور على اسم مطابق في TradingEconomics (commodities/search)",
            }
            continue

        week_pct, mode = extract_weekly_pct(found)
        src_name = found.get("Name")

        if week_pct is None:
            per_item[item] = {
                "week_pct": None,
                "level": "⚪ غير متاح",
                "src_name": src_name,
                "mode": "none",
                "reason": "تم العثور على الاسم لكن لا توجد قيم تغيّر (Weekly/Monthly/Daily) للاشتقاق",
            }
            continue

        prev_week = state.get("last_week_pct", {}).get(item, week_pct)
        delta = float(week_pct) - float(prev_week)

        # علامة تقديري
        approx_tag = ""
        if mode == "est_m":
            approx_tag = "≈"
        elif mode == "est_d":
            approx_tag = "≈"

        per_item[item] = {
            "week_pct": float(week_pct),
            "level": level_from_weekly_change(float(week_pct)),
            "trend": f"{trend_arrow(1 if delta>0 else (-1 if delta<0 else 0))} ({delta:+.1f}%)",
            "src_name": src_name,
            "mode": mode,
            "approx_tag": approx_tag,
        }

    ranked = []
    for item, v in per_item.items():
        if v.get("week_pct") is None:
            continue
        ranked.append((item, float(v["week_pct"]), v.get("level", "")))
    ranked.sort(key=lambda x: x[1], reverse=True)

    unified = compute_unified_index(per_item)

    if "last_unified" not in state:
        overall_tr = "— أول قراءة"
        overall_lvl = overall_level(unified)
    else:
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
        src = v.get("src_name")
        exp = format_exposure(EXPOSURE.get(item, []))
        approx = v.get("approx_tag", "")

        if pct is None:
            lines.append(f"• {item}: {lvl} | بيانات سعر غير متاحة حاليًا")
            if v.get("reason"):
                lines.append(f"  السبب: {v['reason']}")
            if src:
                lines.append(f"  مصدر TE: {src}")
        else:
            lines.append(f"• {item}: {lvl} | {approx}{pct:+.1f}% (7d) | {tr}")
            if src:
                lines.append(f"  مصدر TE: {src}")
            if v.get("mode") in ("est_m", "est_d"):
                lines.append("  ملاحظة: النسبة أسبوعية تقديرية (اشتقاق)")

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

    state["last_unified"] = unified
    state.setdefault("last_week_pct", {})
    for item in COMMODITIES:
        if per_item[item].get("week_pct") is not None:
            state["last_week_pct"][item] = per_item[item]["week_pct"]
    state["last_update"] = now
    save_state(state)

if __name__ == "__main__":
    main()
