#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import math
import datetime
from typing import Dict, List, Tuple, Optional

import requests

# =========================
# إعدادات تيليجرام
# =========================
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

if not BOT_TOKEN or not CHAT_ID:
    raise SystemExit("Missing env vars: TELEGRAM_BOT_TOKEN and/or TELEGRAM_CHAT_ID")

# =========================
# إعدادات عامة
# =========================
STATE_FILE = "dust_state.json"
KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))

# مدن + إحداثيات (تقدر تزيد/تعدل)
CITIES = [
    ("الرياض", 24.7136, 46.6753),
    ("جدة", 21.4858, 39.1925),
    ("مكة", 21.3891, 39.8579),
    ("الدمام", 26.4207, 50.0888),
    ("الأحساء", 25.3833, 49.5833),
    ("القصيم", 26.2077, 43.4837),  # بريدة تقريباً
    ("حائل", 27.5114, 41.7208),
    ("سكاكا", 29.9697, 40.2064),
    ("الباحة", 20.0129, 41.4677),
]

# عتبات PM10 (µg/m³) — تقديرية تشغيلية (تقدر تعدلها حسب معاييركم)
THRESHOLDS = {
    "🟢 طبيعي": (0, 80),
    "🟡 متوسط": (80, 150),
    "🟠 مرتفع": (150, 300),
    "🔴 شديد": (300, 10_000),
}

# =========================
# أدوات مساعدة
# =========================

def now_ksa_str() -> str:
    dt = datetime.datetime.now(tz=KSA_TZ)
    # مثال: 2026-03-01 12:53 KSA
    return dt.strftime("%Y-%m-%d %H:%M KSA")

def weekday_ar(dt: datetime.datetime) -> str:
    # بسيط: تحويل اسم اليوم
    mapping = {
        0: "الاثنين",
        1: "الثلاثاء",
        2: "الأربعاء",
        3: "الخميس",
        4: "الجمعة",
        5: "السبت",
        6: "الأحد",
    }
    return mapping.get(dt.weekday(), "")

def load_state() -> Dict:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_state(state: Dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def classify_pm10(pm10: float) -> str:
    for label, (lo, hi) in THRESHOLDS.items():
        if lo <= pm10 < hi:
            return label
    return "🟠 مرتفع"

def dust_index(pm10_max: float) -> int:
    """
    تحويل PM10 لأقرب مؤشر 0..100 بشكل تشغيلي.
    - تحت 80: منخفض
    - 80..300: يرتفع تدريجياً
    - فوق 300: يقفل 100 بسرعة
    """
    if pm10_max <= 0:
        return 0
    if pm10_max < 80:
        return int(round((pm10_max / 80) * 25))
    if pm10_max < 300:
        # من 25 إلى 85 تقريباً
        x = (pm10_max - 80) / (300 - 80)
        return int(round(25 + x * 60))
    # فوق 300: 85..100
    # نستخدم دالة لوجاريتمية بسيطة
    extra = min(15, int(round(15 * math.log10(1 + (pm10_max - 300) / 100))))
    return min(100, 85 + extra)

def trend_text(current_idx: int, prev_idx: Optional[int]) -> Tuple[str, str]:
    """
    يرجع:
    - رمز الاتجاه (↗/↘/↔)
    - نص (+/-delta)
    """
    if prev_idx is None:
        return "↔", "(بدون مقارنة)"
    delta = current_idx - prev_idx
    if abs(delta) <= 2:
        return "↔", f"(+{delta})" if delta >= 0 else f"({delta})"
    if delta > 0:
        return "↗", f"(+{delta})"
    return "↘", f"({delta})"

def risk_level_from_label(label: str) -> str:
    # مستوى الخطر العام يساوي أعلى تصنيف
    return label

def pick_readiness_level(risk_label: str) -> str:
    if risk_label.startswith("🔴"):
        return "Level 2"
    if risk_label.startswith("🟠"):
        return "Level 1"
    return "Level 0"

def operational_impact(risk_label: str) -> str:
    if risk_label.startswith("🔴"):
        return "انخفاض الرؤية + إجهاد تنفسي محتمل"
    if risk_label.startswith("🟠"):
        return "تراجع جودة الهواء + تحذير للأنشطة الخارجية"
    if risk_label.startswith("🟡"):
        return "ملاحظة جودة الهواء (احتياطات خفيفة)"
    return "لا تأثير تشغيلي متوقع"

def operational_analysis(max_city: str, risk_label: str) -> str:
    if risk_label.startswith("🔴"):
        return (
            "• موجة غبار/جسيمات مرتفعة تؤثر على عدة مناطق.\n"
            f"• أعلى تركّز مسجل حالياً في {max_city}.\n"
            "• تأثير محتمل على الأنشطة الخارجية والتنقل، خاصةً للفئات الحساسة."
        )
    if risk_label.startswith("🟠"):
        return (
            "• مستويات غبار مرتفعة في بعض المناطق.\n"
            f"• أعلى تركّز مسجل حالياً في {max_city}.\n"
            "• يُنصح بتقليل التعرض المباشر في الهواء الطلق عند الحاجة."
        )
    return (
        "• لا توجد مؤشرات تشغيلية حرجة حالياً.\n"
        f"• أعلى تركّز مسجل حالياً في {max_city}.\n"
        "• الاستمرار في الرصد حسب الجدولة."
    )

def open_meteo_fetch_pm10(lat: float, lon: float) -> Optional[float]:
    """
    يجلب آخر قيمة PM10 (hourly) من Open-Meteo Air Quality.
    ملاحظة: Open-Meteo يرجع hourly arrays. نأخذ آخر قيمة non-null.
    """
    url = "https://air-quality-api.open-meteo.com/v1/air-quality"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "pm10",
        "timezone": "Asia/Riyadh",
    }
    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
        hourly = data.get("hourly", {})
        values = hourly.get("pm10", [])
        if not values:
            return None
        # آخر قيمة غير None
        for v in reversed(values):
            if v is not None:
                return float(v)
        return None
    except Exception:
        return None

def format_city_groups(city_values: List[Tuple[str, float]]) -> str:
    """
    يقسم المدن حسب التصنيف ويطبعها مثل:
    🔴 شديد:
    • الرياض: 1967 µg/m³
    ...
    """
    groups: Dict[str, List[Tuple[str, float]]] = {k: [] for k in THRESHOLDS.keys()}
    for name, pm10 in city_values:
        label = classify_pm10(pm10)
        groups.setdefault(label, []).append((name, pm10))

    # ترتيب داخل كل مجموعة تنازلي
    for k in groups:
        groups[k].sort(key=lambda x: x[1], reverse=True)

    # نطبع فقط المجموعات اللي فيها عناصر (وبالترتيب من الأعلى للأسفل)
    order = ["🔴 شديد", "🟠 مرتفع", "🟡 متوسط", "🟢 طبيعي"]
    lines = ["════════════════════", "📍 المناطق الأعلى تأثراً (PM10)"]
    for key in order:
        items = groups.get(key, [])
        if not items:
            continue
        lines.append("")
        lines.append(f"{key}:")
        for name, pm10 in items:
            lines.append(f"• {name}: {int(round(pm10))} µg/m³")
    return "\n".join(lines)

def send_telegram(text: str) -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "disable_web_page_preview": True,
    }
    r = requests.post(url, json=payload, timeout=20)
    r.raise_for_status()

# =========================
# Main
# =========================

def main():
    # 1) Fetch
    city_values: List[Tuple[str, float]] = []
    failed: List[str] = []

    for name, lat, lon in CITIES:
        pm10 = open_meteo_fetch_pm10(lat, lon)
        if pm10 is None:
            failed.append(name)
            continue
        city_values.append((name, pm10))

    if not city_values:
        # لو فشل كل شيء
        msg = (
            "🚨 تقرير الغبار التشغيلي – المملكة العربية السعودية\n"
            f"🕒 {now_ksa_str()}\n"
            "════════════════════\n"
            "⚠️ تعذر جلب بيانات PM10 حالياً.\n"
            "• السبب المحتمل: فشل API أو اتصال الشبكة.\n"
            "• الإجراء: إعادة المحاولة بالتشغيل القادم."
        )
        send_telegram(msg)
        return

    # 2) Compute max + classification
    city_values.sort(key=lambda x: x[1], reverse=True)
    max_city, max_val = city_values[0]
    risk_label = classify_pm10(max_val)
    idx = dust_index(max_val)

    # 3) Trend vs previous
    state = load_state()
    prev_idx = state.get("last_index")
    arrow, delta_txt = trend_text(idx, prev_idx)

    # Save state
    state["last_index"] = idx
    state["last_max_city"] = max_city
    state["last_max_pm10"] = float(max_val)
    state["last_run_ksa"] = now_ksa_str()
    save_state(state)

    # 4) Build blocks
    dt_now = datetime.datetime.now(tz=KSA_TZ)
    header = (
        "🚨 تقرير الغبار التشغيلي – المملكة العربية السعودية\n"
        f"🕒 {weekday_ar(dt_now)} | {dt_now.strftime('%Y-%m-%d')} | {dt_now.strftime('%H:%M')} KSA"
    )

    executive_block = (
        "════════════════════\n"
        "📊 التقييم التنفيذي السريع\n"
        f"📌 مستوى الخطر العام: {risk_level_from_label(risk_label)}\n"
        f"📊 مؤشر الغبار: {idx}/100\n"
        f"📈 الاتجاه التشغيلي: {arrow} مستقر {delta_txt}\n"
        f"🌫️ التأثير المتوقع: {operational_impact(risk_label)}\n"
        f"🏥 مستوى الجاهزية المقترح: {pick_readiness_level(risk_label)}\n"
        f"📍 الأعلى: {max_city} ({int(round(max_val))} µg/m³)"
    )

    cities_block = format_city_groups(city_values)

    analysis_block = (
        "════════════════════\n"
        "🧠 التفسير التشغيلي\n"
        f"{operational_analysis(max_city, risk_label)}"
    )

    action_block = (
        "════════════════════\n"
        "⚡ توصيات تشغيلية\n"
        "• رفع الجاهزية حسب الإجراءات الداخلية.\n"
        "• تقليل الأعمال الميدانية غير الضرورية.\n"
        "• متابعة التحديث القادم حسب الجدولة.\n"
        "\n"
        "════════════════════\n"
        "🛰️ المصدر: Open-Meteo Air Quality (PM10)\n"
    )

    if failed:
        action_block += f"ℹ️ مدن تعذر جلبها: {', '.join(failed)}\n"

    msg = "\n\n".join([header, executive_block, cities_block, analysis_block, action_block])

    # 5) Send
    send_telegram(msg)

if __name__ == "__main__":
    main()
