def _build_report_text(report_title, grouped, include_ais=True):

    text = []

    text.append(report_title)
    text.append("")
    text.append("════════════════════")

    # ======================
    # GDACS
    # ======================
    text.append("3️⃣ الكوارث الطبيعية (GDACS)")
    text += _lines_from_titles(grouped.get("gdacs", []))
    text.append("")

    # ======================
    # FIRMS
    # ======================
    text.append("4️⃣ حرائق الغابات (FIRMS)")
    text += _lines_from_titles(grouped.get("fires", []))
    text.append("")

    # ======================
    # UKMTO
    # ======================
    text.append("5️⃣ الأحداث والتحذيرات البحرية (UKMTO)")
    text += _lines_from_titles(grouped.get("ukmto", []))
    text.append("")

    # ======================
    # AIS
    # ======================
    if include_ais:
        text.append("6️⃣ حركة السفن وازدحام الموانئ (AIS)")
        text += _lines_from_titles(grouped.get("ais", []))
        text.append("")

    # ======================
    text.append("7️⃣ ملاحظات تشغيلية")
    text.append("• تم إعداد التقرير آليًا بناءً على مصادر الرصد المعتمدة.")
    text.append("• يتم إصدار تنبيه إضافي عند ظهور أحداث جديدة مؤثرة.")

    return "\n".join(text)
