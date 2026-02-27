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

# --- سلعك ---
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

# مطابقة أسماء TE
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

# --- Yahoo Finance fallback tickers (قوية ومجانية) ---
YF_TICKERS = {
    "القمح": ["ZW=F"],          # Wheat Futures
    "الأرز": ["ZR=F"],          # Rough Rice Futures
    "الذرة": ["ZC=F"],          # Corn Futures
    "السكر": ["SB=F"],          # Sugar Futures
    "الزيت النباتي": ["BO=F"],  # Soybean Oil Futures (proxy قوي للزيوت)
    "الشعير": ["ZC=F", "ZW=F"], # proxy
    "الأعلاف": ["ZM=F", "ZC=F"],# Soybean Meal Futures, ثم corn
    # حليب بودرة: ما له ticker مجاني ثابت وموثوق؛ نخليه حسب TE فقط
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

# مستويات الخطر الأسبوعية
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
    return " | ".join([f"{FLAGS.get(n,'')} {n}".strip() for n in names])

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
    # prefer shortest name (usually the main instrument)
    candidates.sort(key=lambda x: len(str(x.get("Name",""))))
    return candidates[0]

def extract_symbol(it: dict) -> Optional[str]:
    # TE قد يستخدم أكثر من حقل
    for k in ["Symbol", "symbol", "Ticker", "ticker", "Code", "code", "HistoricalDataSymbol", "historicalDataSymbol"]:
        v = it.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None

def extract_weekly_from_snapshot(it: dict) -> Optional[float]:
    w = it.get("WeeklyPercentualChange")
    if w is None:
        return None
    try:
        return float(w)
    except Exception:
        return None

def te_weekly_from_historical(symbol: str) -> Optional[float]:
    """
    يحاول جلب تاريخ أسعار (close) وحساب التغير على ~7 جلسات تداول.
    TradingEconomics markets historical endpoint موجود رسميًا.  [oai_citation:2‡Trading Economics API](https://docs.tradingeconomics.com/markets/historical/?utm_source=chatgpt.com)
    """
    # جرّب صيغ محتملة للـ endpoint (التوثيق يختلف حسب الـ symbol)
    candidates = [
        f"{TE_BASE}/markets/historical/{symbol}?c={TE_API_KEY}&f=json",
        f"{TE_BASE}/markets/historical/{symbol}:commodity?c={TE_API_KEY}&f=json",
        f"{TE_BASE}/markets/historical/{symbol}/commodity?c={TE_API_KEY}&f=json",
    ]
    for url in candidates:
        data = te_get_json(url)
        if not isinstance(data, list) or len(data) < 8:
            continue

        # نحاول استخراج close/price
        closes = []
        for row in data:
            if not isinstance(row, dict):
                continue
            for ck in ["Close", "close", "Price", "price", "Value", "value", "Observed", "observed", "Last", "last"]:
                if row.get(ck) is not None:
                    try:
                        closes.append(float(row.get(ck)))
                        break
                    except Exception:
                        pass

        if len(closes) >= 8:
            last = closes[-1]
            prev = closes[-8]
            if prev != 0:
                return ((last - prev) / prev) * 100.0

    return None

# ========== Yahoo Finance fallback ==========
def yf_chart_closes(ticker: str) -> Optional[List[float]]:
    """
    Yahoo chart endpoint: /v8/finance/chart/{symbol}.  [oai_citation:3‡Hexdocs](https://hexdocs.pm/quant/Quant.Explorer.Providers.YahooFinance.html?utm_source=chatgpt.com)
    """
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    params = {"interval": "1d", "range": "15d"}  # enough for 7 trading days
    try:
        r = requests.get(url, params=params, timeout=45)
        r.raise_for_status()
        js = r.json()
        result = js.get("chart", {}).get("result", [])
        if not result:
            return None
        closes = result[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
        # clean None values
        closes = [float(x) for x in closes if x is not None]
        if len(closes) < 8:
            return None
        return closes
    except Exception:
        return None

def weekly_from_yahoo(tickers: List[str]) -> Tuple[Optional[float], Optional[str]]:
    for t in tickers:
        closes = yf_chart_closes(t)
        if not closes:
            continue
        last = closes[-1]
        prev = closes[-8]
        if prev != 0:
            return ((last - prev) / prev) * 100.0, t
    return None, None

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
        found = pick_best_match(all_comms, MATCH_KEYWORDS.get(item, []))

        src_name = found.get("Name") if found else None
        symbol = extract_symbol(found) if found else None

        # 1) try snapshot weekly
        week_pct = extract_weekly_from_snapshot(found) if found else None
        src_mode = "TE-snapshot"

        # 2) try TE historical compute if missing
        if week_pct is None and symbol:
            w2 = te_weekly_from_historical(symbol)
            if w2 is not None:
                week_pct = w2
                src_mode = "TE-historical"

        # 3) fallback to Yahoo Finance for key commodities if still missing
        yf_used = None
        if week_pct is None and item in YF_TICKERS:
            w3, yf_used = weekly_from_yahoo(YF_TICKERS[item])
            if w3 is not None:
                week_pct = w3
                src_mode = "Yahoo"

        if week_pct is None:
            per_item[item] = {
                "week_pct": None,
                "level": "⚪ غير متاح",
                "src_name": src_name,
                "src_mode": src_mode,
                "reason": "المصدر لم يوفّر حقول تغير، ولم ننجح في استخراج تاريخ سعر للحساب الأسبوعي",
            }
            continue

        prev_week = state.get("last_week_pct", {}).get(item, week_pct)
        delta = float(week_pct) - float(prev_week)

        per_item[item] = {
            "week_pct": float(week_pct),
            "level": level_from_weekly_change(float(week_pct)),
            "trend": f"{trend_arrow(1 if delta>0 else (-1 if delta<0 else 0))} ({delta:+.1f}%)",
            "src_name": src_name,
            "src_mode": src_mode,
            "yf": yf_used,
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
            if v.get("src_name"):
                lines.append(f"  مصدر TE: {v['src_name']}")
            if v.get("reason"):
                lines.append(f"  السبب: {v['reason']}")
        else:
            lines.append(f"• {item}: {lvl} | {pct:+.1f}% (7d) | {tr}")
            if v.get("src_mode") == "Yahoo" and v.get("yf"):
                lines.append(f"  مصدر: Yahoo ({v['yf']})")
            elif v.get("src_mode") == "TE-historical":
                lines.append("  مصدر: TradingEconomics (Historical)")
            else:
                if v.get("src_name"):
                    lines.append(f"  مصدر TE: {v['src_name']}")

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

    # Save state
    state["last_unified"] = unified
    state.setdefault("last_week_pct", {})
    for item in COMMODITIES:
        if per_item[item].get("week_pct") is not None:
            state["last_week_pct"][item] = per_item[item]["week_pct"]
    state["last_update"] = now
    save_state(state)

if __name__ == "__main__":
    main()
