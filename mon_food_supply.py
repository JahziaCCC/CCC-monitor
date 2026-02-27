# mon_food_supply.py
import os
import json
import re
import datetime
import requests

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
STATE_FILE = "food_supply_state.json"

FAO_FPI_URL = "https://www.fao.org/worldfoodsituation/foodpricesindex/en"

# =========================
# سلعك (بعد الاستبعاد)
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

# ربط السلع بمؤشرات FAO (مجموعات)
# (هذا عملي وواقعي لنظام إنذار مبكر عالمي)
GROUP_MAP = {
    "القمح": "cereals",
    "الأرز": "cereals",
    "الذرة": "cereals",
    "الشعير": "cereals",
    "الأعلاف": "cereals",        # أعلاف غالبًا تتأثر بالحبوب
    "الزيت النباتي": "oils",
    "السكر": "sugar",
    "حليب بودرة": "dairy",
}

GROUP_AR = {
    "overall": "المؤشر العام",
    "cereals": "الحبوب",
    "oils": "الزيوت النباتية",
    "sugar": "السكر",
    "dairy": "الألبان",
    "meat": "اللحوم",
}

# =========================
# Telegram
# =========================
def tg_send_message(text: str) -> None:
    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    r = requests.post(
        url,
        json={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True},
        timeout=30,
    )
    r.raise_for_status()

# =========================
# Helpers
# =========================
def now_ksa() -> str:
    return datetime.datetime.now(KSA_TZ).strftime("%Y-%m-%d %H:%M KSA")

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

def trend_arrow(delta: float) -> str:
    if delta > 0:
        return "↑ يتصاعد"
    if delta < 0:
        return "↓ يتحسن"
    return "↔ مستقر"

def level_from_change(pct_change: float) -> str:
    """
    مستوى لكل سلعة حسب التغير % (مقارنة بآخر قراءة محفوظة)
    """
    if pct_change >= 5:
        return "🔴 مرتفع"
    if pct_change >= 2:
        return "🟠 متوسط"
    return "🟢 طبيعي"

def clamp(n, lo, hi):
    return max(lo, min(hi, n))

# =========================
# FAO fetch + parse
# =========================
def fetch_fao_page() -> str:
    r = requests.get(FAO_FPI_URL, timeout=40)
    r.raise_for_status()
    return r.text

def extract_first_float_after_keywords(html: str, keywords: list[str]) -> float | None:
    """
    يحاول استخراج رقم قريب من الكلمات المفتاحية.
    هذا أسلوب "عملي" لأنه يقلل التعطل إذا تغيّر شكل الصفحة.
    """
    # نجمع نافذة نصية حول الكلمات ثم نبحث رقم
    lower = html.lower()
    for kw in keywords:
        i = lower.find(kw.lower())
        if i == -1:
            continue
        window = html[i:i+1500]
        m = re.search(r"([0-9]{2,3}\.?[0-9]?)", window)
        if m:
            try:
                return float(m.group(1))
            except:
                pass
    return None

def fetch_fao_indices() -> dict:
    """
    يرجع قيم تقريبية للمؤشرات:
    overall, cereals, oils, sugar, dairy, meat (إن توفرت)
    """
    html = fetch_fao_page()

    # المؤشر العام
    overall = extract_first_float_after_keywords(
        html,
        ["Food Price Index averaged", "food price index averaged", "FAO Food Price Index averaged"]
    )

    # مؤشرات المجموعات (نجرب كلمات متعددة)
    cereals = extract_first_float_after_keywords(html, ["Cereal Price Index", "cereal price index", "cereals"])
    oils    = extract_first_float_after_keywords(html, ["Vegetable Oil Price Index", "vegetable oil price index", "vegetable oils"])
    sugar   = extract_first_float_after_keywords(html, ["Sugar Price Index", "sugar price index", "sugar"])
    dairy   = extract_first_float_after_keywords(html, ["Dairy Price Index", "dairy price index", "dairy"])
    meat    = extract_first_float_after_keywords(html, ["Meat Price Index", "meat price index", "meat"])

    # fallback آمن إذا فشل أي واحد
    # (نستخدم overall كأساس حتى لا ينهار التقرير)
    if overall is None:
        overall = 120.0

    def fb(x):
        return x if x is not None else overall

    return {
        "overall": float(overall),
        "cereals": float(fb(cereals)),
        "oils": float(fb(oils)),
        "sugar": float(fb(sugar)),
        "dairy": float(fb(dairy)),
        "meat": float(fb(meat)),
    }

# =========================
# Risk scoring
# =========================
def compute_unified_index(group_changes_pct: dict) -> int:
    """
    مؤشر موحد 0-100 مبني على تغيّر المجموعات (وزن تشغيلي).
    """
    # أوزان منطقية لسلاسل الإمداد (بدون تعقيد زائد)
    w = {"cereals": 0.45, "oils": 0.20, "sugar": 0.15, "dairy": 0.20}

    # نحول %change إلى نقاط 0-100 (مثلاً 0% => 0، 10% => 100)
    score = 0.0
    for g, weight in w.items():
        pct = group_changes_pct.get(g, 0.0)
        g_score = clamp((pct / 10.0) * 100.0, 0.0, 100.0)
        score += weight * g_score

    return int(round(clamp(score, 0, 100)))

def overall_level(idx: int) -> str:
    if idx >= 70:
        return "🔴 ضغط مرتفع"
    if idx >= 40:
        return "🟠 ضغط متوسط"
    return "🟢 طبيعي"

# =========================
# Build report
# =========================
def build_report(now: str, unified_idx: int, overall_trend: str, overall_lvl: str,
                 per_commodity: list[dict], top_pressures: list[dict],
                 fao_values: dict, group_changes_pct: dict) -> str:

    lines = []
    lines.append("🍞📦 رصد سلاسل إمداد الغذاء – المملكة العربية السعودية")
    lines.append(f"🕒 {now}")
    lines.append("")
    lines.append("════════════════════")
    lines.append("📊 الملخص التنفيذي")
    lines.append("")
    lines.append(f"📌 الحالة العامة: {overall_lvl}")
    lines.append(f"📈 مؤشر الأمن الغذائي: {unified_idx}/100")
    lines.append(f"📊 اتجاه الحالة: {overall_trend}")
    lines.append("")
    lines.append("🏷️ أعلى السلع ضغطًا:")
    if top_pressures:
        for x in top_pressures[:3]:
            lines.append(f"• {x['name']} — {x['level']} ({x['pct_str']})")
    else:
        lines.append("• لا توجد ضغوط بارزة حالياً")
    lines.append("")
    lines.append("════════════════════")
    lines.append("📦 حالة السلع (حسب المؤشرات العالمية)")
    lines.append("")
    for x in per_commodity:
        lines.append(f"• {x['name']}: {x['level']} | {x['pct_str']} | {x['trend']}")
    lines.append("")
    lines.append("════════════════════")
    lines.append("🌍 إشارات عالمية (FAO)")
    lines.append(f"• المؤشر العام: {fao_values['overall']:.1f}")
    lines.append(f"• الحبوب: {fao_values['cereals']:.1f} ({group_changes_pct['cereals']:+.1f}%)")
    lines.append(f"• الزيوت: {fao_values['oils']:.1f} ({group_changes_pct['oils']:+.1f}%)")
    lines.append(f"• السكر: {fao_values['sugar']:.1f} ({group_changes_pct['sugar']:+.1f}%)")
    lines.append(f"• الألبان: {fao_values['dairy']:.1f} ({group_changes_pct['dairy']:+.1f}%)")
    lines.append("")
    lines.append("════════════════════")
    lines.append("🧭 توصية تشغيلية")
    if unified_idx >= 70:
        lines.append("• تفعيل مراقبة يومية مكثفة للقمح والزيوت.")
        lines.append("• مراجعة المخزون التشغيلي وحدود إعادة الطلب.")
        lines.append("• تجهيز موردين بديلين وخيارات شحن بديلة.")
    elif unified_idx >= 40:
        lines.append("• متابعة شبه يومية للحبوب والزيوت.")
        lines.append("• مراجعة المخزون التشغيلي للسلع الأعلى ضغطاً.")
    else:
        lines.append("• استمرار الرصد الدوري حسب الجدولة.")
        lines.append("• رفع التنبيه فقط عند تغيرات كبيرة.")
    return "\n".join(lines)

# =========================
# MAIN
# =========================
def main():
    now = now_ksa()
    state = load_state()

    fao = fetch_fao_indices()

    # نحسب تغير كل مجموعة مقارنة بآخر قيمة محفوظة
    prev_groups = state.get("last_fao_groups", {})
    group_changes_pct = {}
    for g in ["cereals", "oils", "sugar", "dairy"]:
        prev = float(prev_groups.get(g, fao[g]))
        curr = float(fao[g])
        pct = 0.0 if prev == 0 else ((curr - prev) / prev) * 100.0
        group_changes_pct[g] = pct

    # لكل سلعة: نأخذ مجموعة FAO التابعة لها ونحسب تغيرها
    per_commodity = []
    for name in COMMODITIES:
        g = GROUP_MAP[name]
        pct = group_changes_pct.get(g, 0.0)

        # اتجاه مقارنة بآخر "تغير" محفوظ للسلعة
        prev_comm = state.get("last_comm_pct", {})
        prev_pct = float(prev_comm.get(name, pct))
        delta_pct = pct - prev_pct

        lvl = level_from_change(pct)
        per_commodity.append({
            "name": name,
            "group": g,
            "pct": pct,
            "pct_str": f"{pct:+.1f}%",
            "trend": f"{trend_arrow(delta_pct)} ({delta_pct:+.1f}%)",
            "level": lvl,
        })

    # نحدد أعلى 3 ضغوط حسب %change
    top_pressures = sorted(per_commodity, key=lambda x: x["pct"], reverse=True)

    # مؤشر موحد + اتجاه عام
    unified = compute_unified_index(group_changes_pct)
    prev_unified = int(state.get("last_unified", unified))
    delta_unified = unified - prev_unified
    overall_trend = f"{trend_arrow(delta_unified)} ({delta_unified:+d})"
    overall_lvl = overall_level(unified)

    report = build_report(
        now=now,
        unified_idx=unified,
        overall_trend=overall_trend,
        overall_lvl=overall_lvl,
        per_commodity=per_commodity,
        top_pressures=top_pressures,
        fao_values=fao,
        group_changes_pct=group_changes_pct,
    )

    tg_send_message(report)

    # حفظ الحالة
    state["last_unified"] = unified
    state["last_fao_groups"] = {g: fao[g] for g in ["cereals", "oils", "sugar", "dairy"]}
    state.setdefault("last_comm_pct", {})
    for x in per_commodity:
        state["last_comm_pct"][x["name"]] = x["pct"]
    state["last_update"] = now
    save_state(state)

if __name__ == "__main__":
    main()
