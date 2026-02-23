from datetime import datetime, timezone

# =====================================
# أدوات مساعدة
# =====================================

def _now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _gdacs_weight(title: str):
    """
    وزن GDACS حسب علاقتها بالسعودية
    """

    t = (title or "").lower()

    # ذكر السعودية صراحة = تأثير كامل
    if "saudi" in t or "saudi arabia" in t:
        return 1.0

    # غير ذلك = تأثير إقليمي منخفض
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


def _dust_risk_points(dust_events):
    """
    حساب ذكي للغبار:
    حسب الانتشار وليس عدد المدن فقط
    """

    if not dust_events:
        return 0

    cities = set()
    max_pm10 = 0

    for e in dust_events:

        meta = e.get("meta") or {}

        city = meta.get("city")
        if city:
            cities.add(city)

        v = meta.get("max_pm10", meta.get("pm10", 0))
        try:
            v = float(v)
        except:
            v = 0

        if v > max_pm10:
            max_pm10 = v

    n = len(cities)

    # انتشار الغبار
    if n <= 2:
        pts = 10
    elif n <= 4:
        pts = 20
    else:
        pts = 30

    # شدة عالية جداً
    if max_pm10 >= 800:
        pts += 10

    return min(pts, 40)


# =====================================
# بناء التقرير الرسمي
# =====================================

def build_official_report(events, state, report_no):

    risk_score = 0

    gdacs_lines = []
    ukmto_lines = []
    ais_lines = []
    dust_lines = []

    dust_events = []

    # =============================
    # تصنيف الأحداث
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
            risk_score += 15

        elif section == "dust":
            dust_lines.append(f"- {title}")
            dust_events.append(e)

    # ⭐ حساب الغبار الذكي
    risk_score += _dust_risk_points(dust_events)

    risk_score = min(risk_score, 100)

    risk_icon, general_state = _risk_level(risk_score)

    # =============================
    # أبرز حدث
    # =============================

    top_event = "لا يوجد"

    if gdacs_lines:
        top_event = gdacs_lines[0].replace("- ", "")
    elif dust_lines:
        top_event = dust_lines[0].replace("- ", "")

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
    lines.append("📍 المناطق الأكثر تأثرًا:")
    lines.append("- الدول المجاورة" if gdacs_lines else "- داخل المملكة")
    lines.append("- مدن داخل المملكة" if dust_lines else "- لا يوجد")
    lines.append("")
    lines.append("════════════════════")
    lines.append("2️⃣ مؤشرات سلاسل الإمداد الغذائي")
    lines.append("")

    if gdacs_lines or ukmto_lines or ais_lines:
        lines.append("• حدث إقليمي/تشغيلي قد يؤثر على تدفق سلاسل الإمداد.")
    else:
        lines.append("• لا توجد مؤشرات تشغيلية مؤثرة حالياً.")

    lines.append("")
    lines.append("════════════════════")
    lines.append("3️⃣ الكوارث الطبيعية (GDACS)")
    lines.append("")
    lines += gdacs_lines if gdacs_lines else ["- لا يوجد"]

    lines.append("")
    lines.append("════════════════════")
    lines.append("4️⃣ الأحداث والتحذيرات البحرية (UKMTO)")
    lines.append("")
    lines += ukmto_lines if ukmto_lines else ["- لا يوجد"]

    lines.append("")
    lines.append("════════════════════")
    lines.append("5️⃣ حركة السفن وازدحام الموانئ (AIS)")
    lines.append("")
    lines += ais_lines if ais_lines else ["- لا يوجد"]

    lines.append("")
    lines.append("════════════════════")
    lines.append("6️⃣ مؤشرات الغبار وجودة الهواء (PM10)")
    lines.append("")
    lines += dust_lines if dust_lines else ["- لا يوجد"]

    lines.append("")
    lines.append("════════════════════")
    lines.append("7️⃣ ملاحظات تشغيلية")
    lines.append("")
    lines.append("• تم إعداد التقرير آليًا بناءً على مصادر الرصد المعتمدة.")
    lines.append("• يتم إصدار تنبيه إضافي عند ظهور أحداث جديدة مؤثرة.")

    return "\n".join(lines)
