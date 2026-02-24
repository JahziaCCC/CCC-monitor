# report_official.py

from datetime import datetime


# =========================
# Risk Engine
# =========================

def _risk_level(score):
    if score >= 80:
        return "🔴 حرج"
    if score >= 60:
        return "🟠 مرتفع"
    if score >= 30:
        return "🟡 مراقبة"
    return "🟢 منخفض"


def _compute_risk(events):
    score = 0

    for e in events:
        sec = e.get("section", "")

        if sec == "fires":
            score += 50

        elif sec == "gdacs":
            sev = e.get("severity", "Green")

            if sev == "Green":
                score += 5
            elif sev == "Yellow":
                score += 10
            elif sev == "Orange":
                score += 20
            elif sev == "Red":
                score += 30

        elif sec == "ukmto":
            score += 15

        elif sec == "ais":
            score += 10

    return min(score, 100)


# =========================
# Build Report
# =========================

def _section_lines(events, section):
    lines = []

    for e in events:
        if e.get("section") == section:
            lines.append(f"- {e.get('title')}")

    if not lines:
        lines.append("- لا يوجد")

    return lines


def _build_report(events):

    score = _compute_risk(events)
    level = _risk_level(score)

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    text = []

    text.append("📄 تقرير الرصد والتحديث التشغيلي")
    text.append("")
    text.append("════════════════════")
    text.append("1️⃣ الملخص التنفيذي")
    text.append("")
    text.append(f"📊 مؤشر المخاطر الموحد: {score}/100")
    text.append(f"📌 مستوى المخاطر: {level}")
    text.append("")

    # أهم حدث
    if events:
        text.append(f"📍 أبرز حدث خلال آخر 6 ساعات:")
        text.append(events[0].get("title"))
    else:
        text.append("📍 أبرز حدث خلال آخر 6 ساعات:")
        text.append("لا يوجد")

    text.append("")
    text.append("════════════════════")
    text.append("2️⃣ مؤشرات سلاسل الإمداد الغذائي")
    text += _section_lines(events, "food")

    text.append("")
    text.append("════════════════════")
    text.append("3️⃣ الكوارث الطبيعية")
    text += _section_lines(events, "gdacs")

    text.append("")
    text.append("════════════════════")
    text.append("4️⃣ حرائق الغابات")
    text += _section_lines(events, "fires")

    text.append("")
    text.append("════════════════════")
    text.append("5️⃣ الأحداث والتحذيرات البحرية")
    text += _section_lines(events, "ukmto")

    text.append("")
    text.append("════════════════════")
    text.append("6️⃣ حركة السفن وازدحام الموانئ")
    text += _section_lines(events, "ais")

    text.append("")
    text.append("════════════════════")
    text.append("7️⃣ ملاحظات تشغيلية")
    text.append("• تم إعداد التقرير آليًا بناءً على مصادر الرصد المعتمدة.")

    return "\n".join(text)


# =========================
# IMPORTANT (run function)
# =========================

def run(events):
    """
    هذه الدالة هي اللي main.py يستدعيها
    """
    report_text = _build_report(events)

    print(report_text)

    return report_text
