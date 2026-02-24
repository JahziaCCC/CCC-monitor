def run(report_title="📄 تقرير الرصد والتحديث التشغيلي",
        only_if_new=False,
        include_ais=True,
        events=None):

    now = _now_ksa()
    report_id = now.strftime("RPT-%Y%m%d-%H%M%S")

    events = events or []
    grouped = _group_events(events)

    food_lines = _lines_from_titles(grouped.get("food", []))
    gdacs_lines = _lines_from_titles(grouped.get("gdacs", []))
    fires_lines = _lines_from_titles(grouped.get("fires", []))
    ukmto_lines = _lines_from_titles(grouped.get("ukmto", []))
    ais_lines = _lines_from_titles(grouped.get("ais", [])) if include_ais else ["- لا يوجد"]

    top_event = "لا يوجد"
    if grouped.get("fires"):
        top_event = grouped["fires"][0].get("title", "لا يوجد")
    elif grouped.get("gdacs"):
        top_event = grouped["gdacs"][0].get("title", "لا يوجد")

    score = 0
    if grouped.get("fires"):
        score += 40
    if grouped.get("gdacs"):
        score += 15
    if grouped.get("ukmto"):
        score += 10
    if grouped.get("ais"):
        score += 10

    score = max(0, min(100, score))

    if score >= 80:
        level = "🔴 حرج"
    elif score >= 60:
        level = "🟠 مرتفع"
    elif score >= 40:
        level = "🟡 مراقبة"
    else:
        level = "🟢 منخفض"

    text = f"""📄 تقرير الرصد والتحديث التشغيلي
رقم التقرير: {report_id}

🕒 تاريخ ووقت التحديث: {now.strftime('%Y-%m-%d %H:%M KSA')}

════════════════════
1️⃣ الملخص التنفيذي

📊 مؤشر المخاطر الموحد: {score}/100
📌 مستوى المخاطر: {level}

📍 أبرز حدث خلال آخر 6 ساعات:
{top_event}

════════════════════
2️⃣ مؤشرات سلاسل الإمداد الغذائي
{chr(10).join(food_lines)}

════════════════════
3️⃣ الكوارث الطبيعية
{chr(10).join(gdacs_lines)}

════════════════════
4️⃣ حرائق الغابات
{chr(10).join(fires_lines)}

════════════════════
5️⃣ الأحداث والتحذيرات البحرية
{chr(10).join(ukmto_lines)}

════════════════════
6️⃣ حركة السفن وازدحام الموانئ
{chr(10).join(ais_lines)}

════════════════════
7️⃣ ملاحظات تشغيلية
• تم إعداد التقرير آليًا.
"""

    _tg_send(text)
    return text
