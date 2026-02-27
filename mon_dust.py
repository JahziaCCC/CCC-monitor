def build_dust_report(now, dust_index, highest_level, highest_city, highest_value,
                      severe_list, high_list):

    lines = []

    # =========================
    # Header
    # =========================
    lines.append("🚨 تنبيه غبار – المملكة العربية السعودية")
    lines.append(f"🕒 {now}")
    lines.append("")

    # =========================
    # Summary
    # =========================
    lines.append(f"📌 أعلى مستوى مسجّل: {highest_level}")
    lines.append(f"📊 مؤشر الغبار: {dust_index}/100")
    lines.append(f"📍 الأعلى: {highest_city} ({highest_value} µg/m³)")
    lines.append("")

    lines.append("════════════════════")

    # =========================
    # Severe
    # =========================
    if severe_list:
        lines.append("🔴 شديد:")
        for city, value in severe_list:
            lines.append(f"• {city}: {value} µg/m³")
        lines.append("")

    # =========================
    # High
    # =========================
    if high_list:
        lines.append("🟠 مرتفع:")
        for city, value in high_list:
            lines.append(f"• {city}: {value} µg/m³")
        lines.append("")

    # =========================
    # Operational Recommendation
    # =========================
    lines.append("")
    lines.append("✅ توصية تشغيلية سريعة:")
    lines.append("• رفع الجاهزية حسب الإجراءات الداخلية.")
    lines.append("• متابعة التحديث القادم حسب الجدولة.")

    return "\n".join(lines)
