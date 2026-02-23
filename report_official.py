from datetime import datetime, timezone

# =====================================
# أدوات مساعدة
# =====================================

def _now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _gdacs_weight(title: str):
    """
    وزن حدث GDACS حسب القرب من السعودية
    """

    t = title.lower()

    # داخل السعودية = وزن كامل
    if "saudi" in t or "saudi arabia" in t:
        return 1.0

    # دول مجاورة = تأثير متوسط
    neighbors = [
        "iran", "iraq", "jordan",
        "kuwait", "qatar", "oman",
        "yemen", "uae", "turkiye",
        "egypt"
    ]

    if any(n in t for n in neighbors):
        return 0.6

    # حدث إقليمي واسع
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


# =====================================
# بناء التقرير الرسمي
# =====================================

def build_official_report(events, state, report_no):

    risk_score = 0

    gdacs_lines = []
    ukmto_lines = []
    ais_lines = []
    dust_lines = []

    # =============================
    # تصنيف الأحداث
    # =============================

    for e in events:

        section = e.get("section", "")
        title = e.get("title", "")

        if section == "gdacs":
            gdacs_lines.append(f"- {title}")

            # ⭐ حساب ذكي للمخاطر
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
            risk_score += 10

    # سقف المخاطر
    if risk_score > 100:
        risk_score = 100

    risk_icon, general_state = _risk_level(risk_score)

    # =============================
    # الملخص التنفيذي
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
    lines.append("- الدول المجاورة")
    lines.append("- مدن داخل المملكة")
    lines.append("")
    lines.append("════════════════════")
    lines.append("2️⃣ مؤشرات سلاسل الإمداد الغذائي")
    lines.append("")

    if gdacs_lines:
        lines.append("• حدث إقليمي قد يؤثر على تدفق سلاسل الإمداد.")
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
