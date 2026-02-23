# report_official.py
from datetime import datetime, timezone
from typing import List

from risk_food import food_supply_summary

# ==============================
# إعدادات بسيطة قابلة للتعديل
# ==============================
SEVERE_DUST_PM10 = 3000  # إذا تجاوزت أعلى قراءة هذا الرقم -> نضيف تنبيه داخل التقرير


# =====================================
# أدوات مساعدة
# =====================================
def _now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _gdacs_weight(title: str):
    t = (title or "").lower()
    if "saudi" in t or "saudi arabia" in t:
        return 1.0
    return 0.3


def _risk_level(score):
    if score >= 75:
        return "🔴 حرج", "حرجة"
    elif score >= 50:
        return "🟠 مرتفع", "نشاط مرتفع"
    elif score >= 25:
        return "🟡 مراقبة", "مراقبة"
    else:
        return "🟢 منخفض", "هادئة"


def _gdacs_mentions_saudi(gdacs_lines: List[str]):
    for line in gdacs_lines:
        t = (line or "").lower()
        if "saudi" in t or "saudi arabia" in t:
            return True
    return False


def _top_dust_event(dust_events):
    best_title = None
    best_val = -1
    for e in dust_events:
        meta = e.get("meta") or {}
        v = meta.get("max_pm10", meta.get("pm10", 0))
        try:
            v = float(v)
        except Exception:
            v = 0
        if v > best_val:
            best_val = v
            best_title = e.get("title", "")
    return best_title or "لا يوجد"


def _dust_summary(dust_events):
    if not dust_events:
        return None

    cities = set()
    max_city = None
    max_pm10 = -1

    for e in dust_events:
        meta = e.get("meta") or {}
        city = meta.get("city")
        if city:
            cities.add(city)

        v = meta.get("max_pm10", meta.get("pm10", 0))
        try:
            v = float(v)
        except Exception:
            v = 0

        if v > max_pm10:
            max_pm10 = v
            max_city = city or ""

    return {
        "count": len(cities) if cities else len(dust_events),
        "max_city": max_city,
        "max_pm10": int(max_pm10) if max_pm10 >= 0 else None
    }


def _dust_risk_points(dust_events):
    if not dust_events:
        return 0

    summary = _dust_summary(dust_events) or {}
    n = summary.get("count", 0)
    max_pm10 = summary.get("max_pm10", 0) or 0

    if n <= 2:
        pts = 10
    elif n <= 4:
        pts = 20
    else:
        pts = 30

    if max_pm10 >= 800:
        pts += 10

    return min(pts, 40)


def _fires_risk_points(fire_events):
    if not fire_events:
        return 0
    meta = (fire_events[0].get("meta") or {})
    count = int(meta.get("count", 0) or 0)
    max_frp = float(meta.get("max_frp", 0) or 0)

    pts = 10
    if count >= 50:
        pts += 10
    if max_frp >= 50:
        pts += 10

    return min(pts, 30)


def _extract_ais_total(ais_events):
    if not ais_events:
        return 0
    meta = (ais_events[0].get("meta") or {})
    try:
        return int(meta.get("total", 0) or 0)
    except Exception:
        return 0


def _operational_explanation(risk_score, gdacs_lines, dust_events, ukmto_lines, ais_events, fire_events):
    bullets = []

    dust_pts = _dust_risk_points(dust_events)
    gdacs_pts = int(30 * _gdacs_weight((gdacs_lines[0] if gdacs_lines else "")))
    ukmto_pts = 20 if ukmto_lines else 0
    ais_pts = 15 if ais_events else 0
    fires_pts = _fires_risk_points(fire_events)

    contribs = [
        ("الغبار داخل المملكة", dust_pts),
        ("GDACS (كوارث طبيعية)", gdacs_pts if gdacs_lines else 0),
        ("UKMTO (بحري)", ukmto_pts),
        ("AIS (الموانئ/الحركة)", ais_pts),
        ("حرائق داخل المملكة", fires_pts),
    ]
    contribs_sorted = sorted(contribs, key=lambda x: x[1], reverse=True)
    main_factor, main_pts = contribs_sorted[0]

    if main_pts > 0:
        bullets.append(f"• العامل الرئيسي: {main_factor}.")

    if dust_events:
        s = _dust_summary(dust_events) or {}
        c = s.get("count")
        mc = s.get("max_city")
        mv = s.get("max_pm10")
        if c and mc and mv is not None:
            bullets.append(f"• الغبار: {c} مدن متأثرة — أعلى قراءة: {mc} ({mv} µg/m³).")
        elif c:
            bullets.append(f"• الغبار: {c} مدن متأثرة داخل المملكة.")

    if fire_events:
        meta = (fire_events[0].get("meta") or {})
        c = meta.get("count")
        mx = meta.get("max_frp")
        if c is not None and mx is not None:
            bullets.append(f"• الحرائق: {c} رصد — أعلى FRP: {float(mx):.1f} (آخر 6 ساعات).")
        else:
            bullets.append("• الحرائق: نشاط مرصود داخل المملكة (متابعة).")

    if gdacs_lines:
        if _gdacs_mentions_saudi(gdacs_lines):
            bullets.append("• GDACS: حدث يذكر المملكة — تأثير أعلى.")
        else:
            bullets.append("• GDACS: حدث إقليمي للتوعية — لا يوجد ذكر مباشر للمملكة (تأثير منخفض).")

    if ukmto_lines:
        bullets.append("• UKMTO: تحذيرات بحرية نشطة — تتطلب متابعة.")

    if ais_events:
        total = _extract_ais_total(ais_events)
        bullets.append(f"• AIS: إجمالي سفن داخل نطاقات الموانئ المحددة: {total}.")

    if not bullets:
        bullets.append("• لا توجد عوامل تشغيلية مؤثرة حالياً.")

    return bullets


# =====================================
# بناء التقرير الرسمي
# =====================================
def build_official_report(events, state, report_no):

    risk_score = 0

    gdacs_lines = []
    ukmto_lines = []
    dust_lines = []
    fires_lines = []
    ais_lines = []

    dust_events = []
    fire_events = []
    ais_events = []

    # =============================
    # تصنيف الأحداث + حساب المخاطر
    # =============================
    for e in events:
        section = e.get("section", "")
        title = e.get("title", "")

        if section == "gdacs":
            gdacs_lines.append(f"- {title}")
            w = _gdacs_weight(title)
            risk_score += int(30 * w)

        elif section == "ukmto":
            ukmto_lines.append(f"- {title}")
            risk_score += 20

        elif section == "ais":
            ais_lines.append(f"- {title}")
            ais_events.append(e)
            risk_score += 15

        elif section == "dust":
            dust_lines.append(f"- {title}")
            dust_events.append(e)

        elif section == "fires":
            fires_lines.append(f"- {title}")
            fire_events.append(e)

    # risk contributions
    risk_score += _dust_risk_points(dust_events)
    risk_score += _fires_risk_points(fire_events)
    risk_score = min(risk_score, 100)

    risk_icon, general_state = _risk_level(risk_score)

    # =============================
    # أبرز حدث خلال آخر 6 ساعات
    # (لو GDACS يذكر السعودية → GDACS، وإلا أعلى غبار داخل المملكة)
    # =============================
    top_event = "لا يوجد"
    if gdacs_lines and _gdacs_mentions_saudi(gdacs_lines):
        top_event = gdacs_lines[0].replace("- ", "")
    elif dust_events:
        top_event = _top_dust_event(dust_events)
    elif fire_events:
        top_event = fire_events[0].get("title", "لا يوجد")
    elif gdacs_lines:
        top_event = gdacs_lines[0].replace("- ", "")

    # =============================
    # تفسير تشغيلي
    # =============================
    expl = _operational_explanation(risk_score, gdacs_lines, dust_events, ukmto_lines, ais_events, fire_events)

    # =============================
    # Food Supply Risk (تحليل مستقل)
    # =============================
    gdacs_mentions = _gdacs_mentions_saudi(gdacs_lines)
    ais_total = _extract_ais_total(ais_events)
    food_lines = food_supply_summary(
        has_gdacs=bool(gdacs_lines),
        gdacs_mentions_saudi=gdacs_mentions,
        has_ukmto=bool(ukmto_lines),
        ais_total=ais_total,
        has_fires=bool(fire_events),
    )

    # =============================
    # تنبيه غبار شديد (داخل التقرير فقط)
    # =============================
    dust_severe_line = None
    dust_sum = _dust_summary(dust_events) if dust_events else None
    if dust_sum and (dust_sum.get("max_pm10") is not None) and (dust_sum.get("max_pm10") >= SEVERE_DUST_PM10):
        city = dust_sum.get("max_city") or "غير محدد"
        val = dust_sum.get("max_pm10")
        dust_severe_line = f"⚠️ تنبيه: غبار شديد جدًا — {city}: {val} µg/m³ (تأثير تشغيلي محتمل)."

    # =============================
    # بناء النص
    # =============================
    lines = []
    lines.append("📄 تقرير الرصد والتحديث التشغيلي")
    lines.append(f"رقم التقرير: {report_no}")
    lines.append("الجهة المصدرة: نظام الرصد الآلي – مركز المتابعة")
    lines.append("تصنيف التقرير: تشغيلي – للاستخدام الداخلي")
    lines.append("")
    lines.append("نطاق الرصد: المملكة والدول المجاورة")
    lines.append(f"🕒 تاريخ ووقت التحديث: {_now_utc()}")
    lines.append("⏱️ آلية التحديث: تلقائي")
    lines.append("")
    lines.append("════════════════════")
    lines.append("1️⃣ الملخص التنفيذي")
    lines.append("")
    lines.append(f"📊 مؤشر المخاطر الموحد: {risk_score}/100")
    lines.append(f"📌 مستوى المخاطر: {risk_icon}")
    lines.append("")
    lines.append(f"📌 الحالة العامة: {general_state}")
    lines.append("📈 مقارنة بالفترة السابقة: — (لا توجد مقارنة سابقة)")
    lines.append("")
    lines.append("📍 أبرز حدث خلال آخر 6 ساعات:")
    lines.append(top_event)
    lines.append("")

    # 🔸 تنبيه الغبار الشديد داخل الملخص (بدون تغيير شكل التقرير)
    if dust_severe_line:
        lines.append(dust_severe_line)
        lines.append("")

    lines.append("🧾 تفسير تشغيلي:")
    lines.extend(expl)
    lines.append("")
    lines.append("📍 المناطق الأكثر تأثرًا:")
    # محلي أولاً إذا الغبار/الحرائق موجودة
    if dust_events or fire_events:
        lines.append("- مدن داخل المملكة")
        if gdacs_lines:
            lines.append("- الدول المجاورة")
    else:
        if gdacs_lines:
            lines.append("- الدول المجاورة")
        lines.append("- مدن داخل المملكة" if dust_lines else "- لا يوجد")
    lines.append("")

    lines.append("════════════════════")
    lines.append("2️⃣ مؤشرات سلاسل الإمداد الغذائي")
    lines.append("")
    lines.extend(food_lines)
    lines.append("")

    lines.append("════════════════════")
    lines.append("3️⃣ الكوارث الطبيعية (GDACS)")
    lines.append("")
    lines += gdacs_lines if gdacs_lines else ["- لا يوجد"]
    lines.append("")

    lines.append("════════════════════")
    lines.append("4️⃣ حرائق الغابات (FIRMS)")
    lines.append("")
    lines += fires_lines if fires_lines else ["- لا يوجد"]
    lines.append("")

    lines.append("════════════════════")
    lines.append("5️⃣ الأحداث والتحذيرات البحرية (UKMTO)")
    lines.append("")
    lines += ukmto_lines if ukmto_lines else ["- لا يوجد"]
    lines.append("")

    lines.append("════════════════════")
    lines.append("6️⃣ حركة السفن وازدحام الموانئ (AIS)")
    lines.append("")
    lines += ais_lines if ais_lines else ["- لا يوجد"]
    lines.append("")

    lines.append("════════════════════")
    lines.append("7️⃣ مؤشرات الغبار وجودة الهواء (PM10)")
    lines.append("")
    lines += dust_lines if dust_lines else ["- لا يوجد"]
    lines.append("")

    lines.append("════════════════════")
    lines.append("8️⃣ ملاحظات تشغيلية")
    lines.append("")
    lines.append("• تم إعداد التقرير آليًا بناءً على مصادر الرصد المعتمدة.")
    lines.append("• يتم إصدار تنبيه إضافي عند ظهور أحداث جديدة مؤثرة.")

    return "\n".join(lines)
