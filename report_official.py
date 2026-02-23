from datetime import datetime, timezone

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


def _gdacs_mentions_saudi(gdacs_lines):
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


def _operational_explanation(risk_score, gdacs_lines, dust_events, ukmto_lines, ais_lines):
    """
    تفسير تشغيلي مختصر يوضح ما الذي رفع/خفض المخاطر
    """
    bullets = []

    # العامل الرئيسي
    dust_pts = _dust_risk_points(dust_events)
    gdacs_pts = int(30 * _gdacs_weight((gdacs_lines[0] if gdacs_lines else "")))
    ukmto_pts = 20 if ukmto_lines else 0
    ais_pts = 15 if ais_lines else 0

    # تحديد أكبر مساهمة
    contribs = [
        ("الغبار داخل المملكة", dust_pts),
        ("GDACS (كوارث طبيعية)", gdacs_pts if gdacs_lines else 0),
        ("UKMTO (بحري)", ukmto_pts),
        ("AIS (ازدحام/حركة موانئ)", ais_pts),
    ]
    contribs_sorted = sorted(contribs, key=lambda x: x[1], reverse=True)
    main_factor, main_pts = contribs_sorted[0]

    if main_pts > 0:
        bullets.append(f"• العامل الرئيسي: {main_factor}.")

    # تفصيل الغبار
    if dust_events:
        s = _dust_summary(dust_events) or {}
        c = s.get("count")
        mc = s.get("max_city")
        mv = s.get("max_pm10")
        if c and mc and mv is not None:
            bullets.append(f"• الغبار: {c} مدن متأثرة — أعلى قراءة: {mc} ({mv} µg/m³).")
        elif c:
            bullets.append(f"• الغبار: {c} مدن متأثرة داخل المملكة.")

    # تفصيل GDACS
    if gdacs_lines:
        if _gdacs_mentions_saudi(gdacs_lines):
            bullets.append("• GDACS: حدث يذكر المملكة — تأثير أعلى.")
        else:
            bullets.append("• GDACS: حدث إقليمي للتوعية — لا يوجد ذكر مباشر للمملكة (تأثير منخفض).")

    # بحري/موانئ
    if ukmto_lines:
        bullets.append("• UKMTO: تحذيرات بحرية نشطة — تتطلب متابعة.")
    if ais_lines:
        bullets.append("• AIS: مؤشرات تشغيلية للموانئ/الحركة البحرية — تتطلب متابعة.")

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
    ais_lines = []
    dust_lines = []

    dust_events = []

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
            risk_score += 15

        elif section == "dust":
            dust_lines.append(f"- {title}")
            dust_events.append(e)

    risk_score += _dust_risk_points(dust_events)
    risk_score = min(risk_score, 100)

    risk_icon, general_state = _risk_level(risk_score)

    # =============================
    # أبرز حدث خلال آخر 6 ساعات
    # =============================
    top_event = "لا يوجد"
    if gdacs_lines and _gdacs_mentions_saudi(gdacs_lines):
        top_event = gdacs_lines[0].replace("- ", "")
    elif dust_events:
        top_event = _top_dust_event(dust_events)
    elif gdacs_lines:
        top_event = gdacs_lines[0].replace("- ", "")

    # =============================
    # تفسير تشغيلي (الإضافة القوية)
    # =============================
    expl = _operational_explanation(risk_score, gdacs_lines, dust_events, ukmto_lines, ais_lines)

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
    lines.append("🧾 تفسير تشغيلي:")
    lines.extend(expl)
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
