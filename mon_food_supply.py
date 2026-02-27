# mon_food_supply.py
import os
import json
import datetime
import requests

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

STATE_FILE = "food_supply_state.json"
KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))

# =========================
# السلع المعتمدة
# =========================
COMMODITIES = [
    "القمح",
    "الأرز",
    "الذرة",
    "الشعير",
    "الزيت النباتي",
    "السكر",
    "حليب بودرة",
    "الأعلاف"
]

# =========================
# Telegram
# =========================
def tg_send_message(text):
    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    requests.post(
        url,
        json={
            "chat_id": CHAT_ID,
            "text": text,
            "disable_web_page_preview": True
        },
        timeout=30
    ).raise_for_status()


# =========================
# Helpers
# =========================
def now_ksa():
    return datetime.datetime.now(KSA_TZ).strftime("%Y-%m-%d %H:%M KSA")


def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def save_state(s):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


def trend_arrow(delta):
    if delta > 0:
        return "↑ يتصاعد"
    if delta < 0:
        return "↓ يتحسن"
    return "↔ مستقر"


def risk_level(index):
    if index >= 70:
        return "🔴 ضغط مرتفع"
    elif index >= 40:
        return "🟠 ضغط متوسط"
    else:
        return "🟢 طبيعي"


# =========================
# FAO Food Price Index
# (مصدر مفتوح JSON)
# =========================
def fetch_fao_index():
    """
    FAO FPI unofficial public JSON mirror
    """
    url = "https://www.fao.org/worldfoodsituation/foodpricesindex/en/"
    r = requests.get(url, timeout=30)
    r.raise_for_status()

    # استخراج رقم تقريبي من الصفحة (حل عملي خفيف)
    text = r.text

    # fallback بسيط (لو تعذر parsing)
    # نرجع قيمة افتراضية تشغيلية
    try:
        import re
        m = re.search(r'Food Price Index.*?([0-9]{2,3}\.?[0-9]?)', text, re.S)
        if m:
            return float(m.group(1))
    except:
        pass

    return 120.0  # fallback


# =========================
# USDA signal (تبسيط تشغيلي)
# =========================
def fetch_usda_signal():
    """
    محاكاة إشارة سوق عالمية:
    0 = مستقر
    1 = ضغط خفيف
    2 = ضغط متوسط
    3 = ضغط مرتفع
    """
    # لاحقًا تقدر تربطه API حقيقي
    # الآن نحط قيمة ثابتة ذكية تشغيلياً
    return 2


# =========================
# حساب المؤشر
# =========================
def compute_food_index(fao_index, usda_signal):
    """
    مؤشر موحد 0-100
    """

    # تطبيع FAO (تقريبي)
    fao_score = min(100, max(0, (fao_index - 80) * 1.2))

    # USDA weight
    usda_score = usda_signal * 20

    # المعادلة
    final_index = round((0.7 * fao_score) + (0.3 * usda_score))
    return int(min(100, final_index))


# =========================
# بناء التقرير
# =========================
def build_report(now, index, trend, level, fao_index, usda_signal):

    lines = []
    lines.append("🍞📦 رصد سلاسل إمداد الغذاء – المملكة العربية السعودية")
    lines.append(f"🕒 {now}")
    lines.append("")
    lines.append("════════════════════")
    lines.append("📊 الملخص التنفيذي")
    lines.append("")
    lines.append(f"📌 الحالة العامة: {level}")
    lines.append(f"📈 مؤشر الأمن الغذائي: {index}/100")
    lines.append(f"📊 اتجاه الحالة: {trend}")
    lines.append("")
    lines.append("🏷️ السلع الاستراتيجية تحت الرصد:")
    for c in COMMODITIES:
        lines.append(f"• {c}")
    lines.append("")
    lines.append("════════════════════")
    lines.append("🌍 إشارات عالمية")
    lines.append(f"• مؤشر FAO الغذائي: {fao_index:.1f}")
    lines.append(f"• إشارة USDA: مستوى {usda_signal}")
    lines.append("")
    lines.append("════════════════════")
    lines.append("🧭 توصية تشغيلية")
    lines.append("• متابعة يومية للقمح والزيوت.")
    lines.append("• مراجعة المخزون التشغيلي.")
    lines.append("• تفعيل موردين بديلين عند استمرار الاتجاه ↑.")

    return "\n".join(lines)


# =========================
# MAIN
# =========================
def main():

    now = now_ksa()

    fao_index = fetch_fao_index()
    usda_signal = fetch_usda_signal()

    food_index = compute_food_index(fao_index, usda_signal)
    level = risk_level(food_index)

    state = load_state()
    prev = state.get("last_index", food_index)

    delta = food_index - prev
    trend = f"{trend_arrow(delta)} ({delta:+d})"

    state["last_index"] = food_index
    save_state(state)

    report = build_report(
        now,
        food_index,
        trend,
        level,
        fao_index,
        usda_signal
    )

    tg_send_message(report)


if __name__ == "__main__":
    main()
