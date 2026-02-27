import os
import io
import csv
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

# ====== Stooq symbols (الأهم) ======
# Stooq غالباً يشتغل مع i=d
STOOQ_SYMBOLS = {
    "القمح": ["zw.f"],
    "الأرز": ["zr.f"],
    "الذرة": ["zc.f"],
    "السكر": ["sb.f"],
    "الزيت النباتي": ["zl.f"],   # Soybean Oil proxy
    "الأعلاف": ["zm.f", "zc.f"], # Soybean Meal ثم Corn
    "الشعير": ["zb.f", "zw.f", "zc.f"],  # barley قد لا يتوفر → fallback
    "حليب بودرة": [],  # غالباً غير متاح مجاناً
}

# TE keywords fallback (عندك Corn/Barley شغالة)
MATCH_KEYWORDS = {
    "القمح": ["wheat"],
    "الأرز": ["rice"],
    "الذرة": ["corn", "maize"],
    "الشعير": ["barley"],
    "الزيت النباتي": ["palm oil", "soybean oil", "rapeseed oil", "sunflower oil", "vegetable oil"],
    "السكر": ["sugar"],
    "حليب بودرة": ["milk", "dairy", "milk powder"],
    "الأعلاف": ["soybean meal", "feed", "corn", "wheat"],
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

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0 Safari/537.36",
    "Accept": "text/csv,application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
}

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

def trend_arrow(delta: float) -> str:
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
    return " | ".join([f"{FLAGS.get(n,'')} {n}".strip() for n in names])

# ========== Stooq ==========
def stooq_fetch_series(symbol: str, days_needed: int = 12) -> Optional[List[float]]:
    # CSV: Date,Open,High,Low,Close,Volume
    url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
    try:
        r = requests.get(url, headers=HTTP_HEADERS, timeout=45)
        if r.status_code != 200:
            return None
        text = r.text.strip()
        if "Date" not in text or "Close" not in text:
            return None

        reader = csv.DictReader(io.StringIO(text))
        closes = []
        for row in reader:
            c = row.get("Close")
            if c is None:
                continue
            try:
                closes.append(float(c))
            except:
                pass

        closes = [x for x in closes if x is not None]
        if len(closes) < days_needed:
            return None
        return closes
    except Exception:
        return None

def weekly_change_from_closes(closes: List[float]) -> Optional[float]:
    # نستخدم آخر 8 إغلاقات (≈ 7 أيام تداول)
    if not closes or len(closes) < 8:
        return None
    last = closes[-1]
    prev = closes[-8]
    if prev == 0:
        return None
    return ((last - prev) / prev) * 100.0

def weekly_from_stooq_list(symbols: List[str]) -> Tuple[Optional[float], Optional[str]]:
    for sym in symbols:
        closes = stooq_fetch_series(sym, days_needed=12)
        if not closes:
            continue
        pct = weekly_change_from_closes(closes)
        if pct is not None:
            return pct, sym
    return None, None

# ========== TE fallback ==========
def te_get_json(url: str) -> Optional[object]:
    try:
        r = requests.get(url, headers=HTTP_HEADERS, timeout=45)
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

def pick_best_match(items: List[dict], keywords: List[str]) -> Optional[dict]:
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
    candidates.sort(key=lambda x: len(str(x.get("Name",""))))
    return candidates[0]

def te_weekly_snapshot(found: dict) -> Optional[float]:
    w = found.get("WeeklyPercentualChange")
    if w is None:
        return None
    try:
        return float(w)
    except:
        return None

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
    te_all = te_fetch_all_commodities()

    per_item: Dict[str, Dict] = {}

    for item in COMMODITIES:
        pct = None
        src = None
        reason = None

        # 1) Stooq first
        syms = STOOQ_SYMBOLS.get(item, [])
        if syms:
            pct, used = weekly_from_stooq_list(syms)
            if pct is not None:
                src = f"Stooq ({used})"

        # 2) TE fallback (snapshot weekly)
        if pct is None:
            found = pick_best_match(te_all, MATCH_KEYWORDS.get(item, []))
            if found:
                w = te_weekly_snapshot(found)
                if w is not None:
                    pct = w
                    src = f"TE ({found.get('Name')})"
                else:
                    reason = "TE لا يعطي WeeklyPercentualChange لهذه السلعة في وضع guest"
            else:
                reason = "لم يتم العثور على السلعة في TE snapshot"

        if pct is None:
            per_item[item] = {
                "week_pct": None,
                "level": "⚪ غير متاح",
                "reason": reason or "لم تتوفر بيانات من Stooq/TE",
            }
            continue

        prev = state.get("last_week_pct", {}).get(item, pct)
        delta = float(pct) - float(prev)

        per_item[item] = {
            "week_pct": float(pct),
            "level": level_from_weekly_change(float(pct)),
            "trend": f"{trend_arrow(delta)} ({delta:+.1f}%)",
            "src": src,
        }

    ranked = [(k, v["week_pct"], v["level"]) for k, v in per_item.items() if v.get("week_pct") is not None]
    ranked.sort(key=lambda x: x[1], reverse=True)

    unified = compute_unified_index(per_item)

    if "last_unified" not in state:
        overall_tr = "— أول قراءة"
    else:
        delta_unified = unified - int(state.get("last_unified", unified))
        overall_tr = f"{trend_arrow(delta_unified)} ({delta_unified:+d})"

    lines = []
    lines.append("🍞📦 رصد سلاسل إمداد الغذاء (B++ أسبوعي – Level 1) – المملكة العربية السعودية")
    lines.append(f"🕒 {now}")
    lines.append("")
    lines.append("════════════════════")
    lines.append("📊 الملخص التنفيذي")
    lines.append("")
    lines.append(f"📌 الحالة العامة: {overall_level(unified)}")
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
            if v.get("reason"):
                lines.append(f"  السبب: {v['reason']}")
        else:
            lines.append(f"• {item}: {lvl} | {pct:+.1f}% (7d) | {tr}")
            if v.get("src"):
                lines.append(f"  مصدر: {v['src']}")

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
