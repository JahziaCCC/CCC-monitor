from datetime import datetime, timezone

SECTION_ORDER = [
    ("gdacs", "3️⃣ الكوارث الطبيعية (GDACS)"),
    ("marine", "4️⃣ الأحداث والتحذيرات البحرية (UKMTO)"),
    ("ports", "5️⃣ حركة السفن وازدحام الموانئ (AIS)"),
    ("dust",  "6️⃣ مؤشرات الغبار وجودة الهواء (PM10)"),
]

def _general_status_score(events):
    score = 0
    for e in events:
        sec = e.get("section", "")
        t = (e.get("title") or "").lower()

        if sec == "marine" or "ukmto" in t:
            score += 3
        elif sec == "ports":
            c = (e.get("meta") or {}).get("count", 0)
            if c >= 30:
                score += 2
        elif sec == "gdacs":
            score += 2
        elif sec == "dust":
            score += 1

    if score >= 7:
        return "نشاط مرتفع", score
    if score >= 3:
        return "نشاط متوسط", score
    return "هادئة", score

def _trend_arrow(score, state):
    if "prev_score" not in state:
        state["prev_score"] = score
        return "— (لا توجد مقارنة سابقة)"

    prev = int(state.get("prev_score", 0))
    if score > prev:
        tr = "↑ تصاعد"
    elif score < prev:
        tr = "↓ تراجع"
    else:
        tr = "→ مستقر"

    state["prev_score"] = score
    return tr

def _top_event(events):
    for sec in ("marine", "ports", "gdacs", "dust"):
        for e in events:
            if e.get("section") != sec:
                continue
            if sec == "ports":
                meta = e.get("meta") or {}
                if meta.get("count", 0) <= 0:
                    continue
                if not meta.get("congested", False):
                    continue
            return e.get("title", "")
    return ""

def _most_affected_areas(events):
    areas = []
    if any(e.get("section") == "marine" for e in events):
        areas.append("البحر الأحمر/الخليج (ملاحة)")
    if any(e.get("section") == "ports" and (e.get("meta") or {}).get("count", 0) > 0 for e in events):
        areas.append("الموانئ")
    if any(e.get("section") == "gdacs" for e in events):
        areas.append("الدول المجاورة")
    if any(e.get("section") == "dust" for e in events):
        areas.append("مدن داخل المملكة")
    return areas[:3]

# ========= Risk Score (0-100) =========
def _risk_score(events):
    score = 0

    for e in events:
        sec = e.get("section", "")
        meta = e.get("meta") or {}
        title = e.get("title", "")

        # dust weight
        if sec == "dust":
            pm = meta.get("max_pm10", meta.get("pm10", 0))
            try:
                pm = float(pm)
            except Exception:
                pm = 0
            if pm >= 500:
                score += 35
            elif pm >= 300:
                score += 25
            elif pm >= 200:
                score += 15
            elif pm >= 150:
                score += 8

        # gdacs weight
        if sec == "gdacs":
            if "RED" in title:
                score += 40
            else:
                score += 20

        # marine weight
        if sec == "marine":
            score += 20

        # ports weight (only if meaningful counts)
        if sec == "ports":
            c = int(meta.get("count", 0))
            if c >= 30:
                score += 20
            elif c >= 15:
                score += 10

    return min(int(score), 100)

def _risk_label(score):
    if score >= 76:
        return "🔴 حرج"
    if score >= 51:
        return "🟠 مرتفع"
    if score >= 21:
        return "🟡 مراقبة"
    return "🟢 هادئ"
# =====================================

def build_official_report(events, state, report_no: str):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    status, _ = _general_status_score(events)
    score_trend = _trend_arrow(_general_status_score(events)[1], state)
    top = _top_event(events)
    areas = _most_affected_areas(events)

    risk = _risk_score(events)
    risk_lbl = _risk_label(risk)

    lines = []
    lines.append("📄 تقرير الرصد والتحديث التشغيلي")
    lines.append(f"رقم التقرير: {report_no}")
    lines.append("الجهة المصدرة: نظام الرصد الآلي – مركز المتابعة")
    lines.append("تصنيف التقرير: تشغيلي – للاستخدام الداخلي")
    lines.append("")
    lines.append("نطاق الرصد: المملكة والدول المجاورة")
    lines.append(f"🕒 تاريخ ووقت التحديث: {now}")
    lines.append("⏱️ آلية التحديث: تلقائي")
    lines.append("")
    lines.append("════════════════════")
    lines.append("1️⃣ الملخص التنفيذي")
    lines.append("")
    lines.append(f"📊 مؤشر المخاطر الموحد: {risk}/100")
    lines.append(f"📌 مستوى المخاطر: {risk_lbl}")
    lines.append("")
    lines.append(f"📌 الحالة العامة: {status}")
    lines.append(f"📈 مقارنة بالفترة السابقة: {score_trend}")
    lines.append("")
    lines.append("📍 أبرز حدث خلال آخر 6 ساعات:")
    lines.append(top if top else "لا توجد أحداث مؤثرة ضمن نطاق الرصد.")
    lines.append("")
    lines.append("📍 المناطق الأكثر تأثرًا:")
    if areas:
        for a in areas:
            lines.append(f"- {a}")
    else:
        lines.append("- لا يوجد")
    lines.append("")
    lines.append("════════════════════")
    lines.append("2️⃣ مؤشرات سلاسل الإمداد الغذائي")
    lines.append("")
    bullets = []
    if any(e.get("section") == "marine" for e in events):
        bullets.append("• تحذير/حادث بحري قد يؤثر على حركة الشحن.")
    if any(e.get("section") == "ports" and (e.get("meta") or {}).get("count", 0) >= 30 for e in events):
        bullets.append("• ازدحام مرتفع في أحد الموانئ.")
    if any(e.get("section") == "dust" for e in events):
        bullets.append("• غبار قوي في مناطق تشغيلية.")
    if bullets:
        lines.extend(bullets)
    else:
        lines.append("• لا توجد مؤشرات تشغيلية مؤثرة حالياً.")
    lines.append("")

    grouped = {}
    for e in events:
        grouped.setdefault(e.get("section", "other"), []).append(e)

    for sec, title in SECTION_ORDER:
        lines.append("════════════════════")
        lines.append(title)
        lines.append("")
        items = grouped.get(sec, [])
        if not items:
            lines.append("- لا يوجد")
            lines.append("")
            continue
        for it in items[:6]:
            lines.append(f"- {it.get('title','')}")
        lines.append("")

    lines.append("════════════════════")
    lines.append("7️⃣ ملاحظات تشغيلية")
    lines.append("")
    lines.append("• تم إعداد التقرير آليًا بناءً على مصادر الرصد المعتمدة.")
    lines.append("• يتم إصدار تنبيه إضافي عند ظهور أحداث جديدة مؤثرة.")
    return "\n".join(lines)
