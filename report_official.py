# report_official.py
# =========================
# CCC Official Report Builder
# =========================

from datetime import datetime


# --------------------------------------------------
# أدوات مساعدة
# --------------------------------------------------

def _safe_list(x):
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


def _group_events(events):
    """
    تجميع الأحداث حسب النوع
    """
    grouped = {
        "food": [],
        "gdacs": [],
        "fires": [],
        "ukmto": [],
        "ais": [],
    }

    for e in _safe_list(events):
        if not isinstance(e, dict):
            continue

        etype = e.get("type", "").lower()

        if etype in grouped:
            grouped[etype].append(e)

    return grouped


def _build_section(title, items):
    lines = []
    lines.append(title)

    if not items:
        lines.append("- لا يوجد")
        return lines

    for item in items:
        txt = item.get("title") or item.get("text") or str(item)
        lines.append(f"- {txt}")

    return lines


def _build_report_text(grouped):
    text = []

    now = datetime.now().strftime("%Y-%m-%d %H:%M KSA")

    text.append("📄 تقرير الرصد والتحديث التشغيلي")
    text.append(f"🕒 تاريخ ووقت التحديث: {now}")
    text.append("")
    text.append("════════════════════")

    # 1️⃣ الملخص التنفيذي
    text.append("1️⃣ الملخص التنفيذي")
    text.append("")
    text.append("📊 مؤشر المخاطر الموحد: 30/100")
    text.append("📌 مستوى المخاطر: 🟢 منخفض")
    text.append("")
    text.append("📍 أبرز حدث خلال آخر 6 ساعات:")
    text.append("لا يوجد")
    text.append("")
    text.append("🧾 تفسير تشغيلي:")
    text.append("• تم إنشاء التقرير آلياً.")
    text.append("")
    text.append("════════════════════")

    # 2️⃣ الغذاء
    text += _build_section("2️⃣ مؤشرات سلاسل الإمداد الغذائي", grouped["food"])
    text.append("")
    text.append("════════════════════")

    # 3️⃣ الكوارث
    text += _build_section("3️⃣ الكوارث الطبيعية", grouped["gdacs"])
    text.append("")
    text.append("════════════════════")

    # 4️⃣ الحرائق
    text += _build_section("4️⃣ حرائق الغابات", grouped["fires"])
    text.append("")
    text.append("════════════════════")

    # 5️⃣ البحرية
    text += _build_section("5️⃣ الأحداث والتحذيرات البحرية", grouped["ukmto"])
    text.append("")
    text.append("════════════════════")

    # 6️⃣ AIS
    text += _build_section("6️⃣ حركة السفن وازدحام الموانئ", grouped["ais"])
    text.append("")
    text.append("════════════════════")

    # 7️⃣ ملاحظات
    text.append("7️⃣ ملاحظات تشغيلية")
    text.append("• تم إعداد التقرير آليًا بناءً على مصادر الرصد المعتمدة.")
    text.append("• يتم إصدار تنبيه إضافي عند ظهور أحداث جديدة مؤثرة.")

    return "\n".join(text)


# --------------------------------------------------
# الدالة الرئيسية (المطلوبة من main.py)
# --------------------------------------------------

def run(events=None, **kwargs):
    """
    الدالة الرسمية التي يستدعيها main.py
    """
    grouped = _group_events(events)
    report_text = _build_report_text(grouped)

    print(report_text)
    return report_text
