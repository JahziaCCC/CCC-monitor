# mon_food_supply.py
import os
import io
import json
import csv
import datetime
from typing import List, Dict, Optional, Tuple

import requests

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
STATE_FILE = "food_supply_state.json"

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

# =========================
# مصادر الأسعار الأسبوعية (Proxies)
# Stooq رموز قد تختلف؛ لذلك وضعنا بدائل.
# الكود يجرب بالترتيب ويأخذ أول رمز يعطي بيانات.
# =========================
PRICE_PROXIES = {
    "القمح":        ["zw.f", "0ap.f", "0aw.f"],   # CBOT Wheat / Wheat alt
    "الذرة":        ["zc.f", "0aq.f"],            # CBOT Corn / Rice alt (fallback)
    "الأرز":        ["zr.f", "0au.f", "0aq.f"],   # Rough Rice / Japonica / Indica
    "الزيت النباتي": ["zl.f", "0ay.f"],           # Soybean Oil / Rapeseed Oil
    "السكر":        ["sb.f", "0am.f"],            # Sugar (raw) / Sugar white
    "حليب بودرة":   ["dxy", "eurusd"],            # لا يوجد مرجع مجاني ثابت — placeholder (سنوضح إن غير متاح)
    "الشعير":       ["zc.f", "zw.f"],             # Proxy: corn/wheat
    "الأعلاف":      ["zc.f", "zw.f"],             # Proxy: corn/wheat
}

# FAO (داعم عالمي)
FAO_FPI_URL = "https://www.fao.org/worldfoodsituation/foodpricesindex/en"

# =========================
# تعرّض الموردين (Countries Exposure)
# طلبك: الهند، باكستان، مصر، تركيا، روسيا، أوكرانيا
# + اقتراحات مهمة: إندونيسيا/ماليزيا (زيوت) ، البرازيل (سكر) ، نيوزيلندا (ألبان)
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
    "الزيت النباتي": ["إندونيسيا", "ماليزيا"],  # اقتراح مهم جدًا للزيوت
    "السكر": ["البرازيل", "الهند"],             # اقتراح مهم جدًا للسكر
    "حليب بودرة": ["نيوزيلندا"],                # مرجع عالمي قوي للألبان
}

# =========================
# إعدادات التقييم (أسبوعي)
# =========================
# مستويات الخطر حسب تغير 7 أيام
THRESH_MED = 2.0   # >= 2% = 🟠
THRESH_HIGH = 5.0  # >= 5% = 🔴

# وزن كل سلعة في المؤشر الموحد
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

# =========================
# Stooq download
# =========================
def _stooq_urls(symbol: str) -> List[str]:
    s = symbol.lower()
    # نماذج شائعة للتنزيل CSV
    return [
        f"https://stooq.com/q/d/l/?s={s}&i=d",
        f"https://stooq.com/q/d/l/?s={s}&i=d&c=0",
        f"https://stooq.com/q/d/?s={s}&c=0",
    ]

def fetch_stooq_daily_close(symbol: str, days_needed: int = 10) -> Optional[List[Tuple[str, float]]]:
    """
    يرجع قائمة (date, close) مرتبة تصاعديًا.
    """
    for url in _stooq_urls(symbol):
        try:
            r = requests.get(url, timeout=40)
            if r.status_code != 200:
                continue
            text = r.text.strip()
            if "Date" not in text and "date" not in text:
                continue

            reader = csv.DictReader(io.StringIO(text))
            rows = []
            for row in reader:
                d = (row.get("Date") or row.get("date") or "").strip()
                c = (row.get("Close") or row.get("close") or "").strip()
                if not d or not c:
                    continue
                try:
                    close = float(c)
                except:
                    continue
                rows.append((d, close))

            if len(rows) >= days_needed:
                rows.sort(key=lambda x: x[0])
                return rows
        except Exception:
            continue

    return None

def weekly_change_from_series(series: List[Tuple[str, float]]) -> Optional[float]:
    """
    يحسب تغير 7 أيام تقريبًا (آخر 6-7 جلسات تداول).
    نأخذ آخر قيمة ونقارنها بقيمة قبل 7 أيام تداول (أو أقرب).
    """
    if not series or len(series) < 8:
        return None
    last = series[-1][1]
    prev = series[-8][1]  # ~7 trading days ago
    if prev == 0:
        return None
    return ((last - prev) / prev) * 100.0

# =========================
# FAO (داعم)
# =========================
def fetch_fao_overall_value() -> Optional[float]:
    """
    استخراج رقم تقريبي للمؤشر العام فقط (داعم).
    """
    try:
        r = requests.get(FAO_FPI_URL, timeout=40)
        r.raise_for_status()
        html = r.text
        import re
        m = re.search(r'Food Price Index.*?([0-9]{2,3}\.?[0-9]?)', html, re.S)
        if m:
            return float(m.group(1))
    except Exception:
        pass
    return None

# =========================
# Build report
# =========================
def format_exposure(names: List[str]) -> str:
    parts = []
    for n in names:
        parts.append(f"{FLAGS.get(n,'')} {n}".strip())
    return " | ".join(parts)

def compute_unified_index(per_item: Dict[str, Dict]) -> int:
    """
    يحول تغيرات أسبوعية إلى مؤشر 0-100.
    قاعدة بسيطة: 0% => 0 ، 10% => 100 (مقصوص).
    """
    score = 0.0
    total_w = 0.0
    for k, w in WEIGHTS.items():
        if k not in per_item:
            continue
        pct = per_item[k].get("week_pct")
        if pct is None:
            continue
        item_score = clamp((pct / 10.0) * 100.0, 0.0, 100.0)
        score += w * item_score
        total_w += w

    if total_w == 0:
        return 0
    return int(round(clamp(score / total_w, 0, 100)))

def main():
    now = now_ksa_str()
    state = load_state()

    # حساب تغير أسبوعي لكل سلعة (من proxies)
    per_item = {}

    for item in COMMODITIES:
        symbols = PRICE_PROXIES.get(item, [])
        series_used = None
        symbol_used = None
        week_pct = None

        # حليب بودرة: ما عندنا proxy مجاني قوي هنا → نخليه غير متاح (إلى أن نربطه بمصدر مناسب)
        if item == "حليب بودرة":
            per_item[item] = {
                "week_pct": None,
                "level": "⚪ غير متاح",
                "symbol": None,
                "trend": "—",
            }
            continue

        for sym in symbols:
            series = fetch_stooq_daily_close(sym, days_needed=10)
            if not series:
                continue
            pct = weekly_change_from_series(series)
            if pct is None:
                continue
            series_used = series
            symbol_used = sym
            week_pct = pct
            break

        if week_pct is None:
            per_item[item] = {
                "week_pct": None,
                "level": "⚪ غير متاح",
                "symbol": symbol_used,
                "trend": "—",
            }
        else:
            prev_week = state.get("last_week_pct", {}).get(item, week_pct)
            delta = week_pct - float(prev_week)

            per_item[item] = {
                "week_pct": float(week_pct),
                "level": level_from_weekly_change(float(week_pct)),
                "symbol": symbol_used,
                "trend": f"{trend_arrow(delta)} ({delta:+.1f}%)",
            }

    # أعلى 3 سلع ضغطًا (حسب التغير الأسبوعي)
    ranked = []
    for item, v in per_item.items():
        if v.get("week_pct") is None:
            continue
        ranked.append((item, v["week_pct"], v["level"]))
    ranked.sort(key=lambda x: x[1], reverse=True)

    # المؤشر الموحد + اتجاهه
    unified = compute_unified_index(per_item)
    prev_unified = int(state.get("last_unified", unified))
    delta_unified = unified - prev_unified
    overall_tr = f"{trend_arrow(delta_unified)} ({delta_unified:+d})"
    overall_lvl = overall_level(unified)

    # FAO (داعم)
    fao_val = fetch_fao_overall_value()
    fao_line = f"{fao_val:.1f}" if isinstance(fao_val, float) else "غير متاح"

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
    lines.append("🌍 إشارات عالمية (داعم)")
    lines.append(f"• مؤشر FAO الغذائي (عام): {fao_line}")
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
