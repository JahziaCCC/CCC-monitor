# report_official.py
import os
import json
import hashlib
import datetime
import requests
import re

STATE_FILE = "mewa_state.json"
KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))

BOT = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ====== عناوين الأقسام (تقدر تعدلها هنا) ======
SECTION_HEADERS = {
    "food":  "2️⃣ مؤشرات سلاسل الإمداد الغذائي",
    # ✅ التعديل المطلوب: عربي بالكامل
    "gdacs": "3️⃣ الكوارث الطبيعية (جي داكس)",
    "fires": "4️⃣ حرائق الغابات (FIRMS)",
    "ukmto": "5️⃣ الأحداث والتحذيرات البحرية (UKMTO)",
    "ais":   "6️⃣ حركة السفن وازدحام الموانئ (AIS)",
}

# عنوان التقرير
REPORT_TITLE = "📄 تقرير الرصد والتحديث التشغيلي"

def _now_ksa():
    return datetime.datetime.now(tz=KSA_TZ)

def _load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_state(state: dict):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def _tg_send(text: str):
    if not BOT or not CHAT_ID:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    r = requests.post(url, json={
        "chat_id": CHAT_ID,
        "text": text,
        "disable_web_page_preview": True
    }, timeout=30)
    r.raise_for_status()

def _group_events(events):
    grouped = {
        "food": [],
        "gdacs": [],
        "fires": [],
        "ukmto": [],
        "ais": [],
        "other": []
    }
    for e in events or []:
        sec = (e.get("section") or "other").lower()
        if sec not in grouped:
            sec = "other"
        grouped[sec].append(e)
    return grouped

def _lines_from_titles(items, limit=12):
    out = []
    for e in items[:limit]:
        t = (e.get("title") or "").strip()
        if t:
            # لا نضيف "- " هنا، لأن التقرير هو اللي يضيفها
            out.append(t)
    return out if out else ["لا يوجد"]

def _extract_main_factor_text(grouped):
    # عامل رئيسي بسيط (من الواقع عندك)
    if grouped["fires"] and any("حرائق" in (x.get("title") or "") for x in grouped["fires"]):
        return "مؤشرات حرائق/نقاط رصد نشطة داخل المملكة (للاطلاع)."
    if grouped["gdacs"] and any("GDACS" in (x.get("title") or "") or "جي داكس" in (x.get("title") or "") for x in grouped["gdacs"]):
        return "حدث إقليمي للتوعية — لا يوجد ذكر مباشر للمملكة (تأثير منخفض)."
    if grouped["ais"] and any("سفينة" in (x.get("title") or "") for x in grouped["ais"]):
        return "مؤشرات ازدحام/حركة بحرية داخل نطاقات المراقبة."
    return "لا توجد مؤشرات داخل المملكة حالياً."

def _pick_highlight(grouped):
    """
    أبرز حدث:
    - إذا فيه Fires headline -> استخدمه
    - وإلا إذا فيه GDACS -> استخدمه
    - وإلا -> لا يوجد
    """
    # Fires headline (عادة أول سطر)
    for e in grouped["fires"]:
        t = (e.get("title") or "").strip()
        if t.startswith("🔥"):
            return t

    # GDACS headline
    for e in grouped["gdacs"]:
        t = (e.get("title") or "").strip()
        if t:
            return t

    return "لا يوجد"

def _calc_risk_index(grouped):
    """
    مؤشر مبسط فقط (بدون تعقيد):
    - Fires موجودة: 40
    - GDACS موجود: 20
    - AIS موجود: 10
    ثم cap 100
    """
    score = 0
    if any((e.get("title") or "").startswith("🔥") for e in grouped["fires"]):
        score += 40
    if any((e.get("title") or "") for e in grouped["gdacs"]):
        score += 20
    if any((e.get("title") or "") for e in grouped["ais"]):
        score += 10

    # حد أدنى تشغيلي
    if score == 0:
        score = 25

    score = max(0, min(100, score))
    if score >= 80:
        level = "🔴 حرج"
    elif score >= 60:
        level = "🟠 مرتفع"
    elif score >= 40:
        level = "🟡 مراقبة"
    else:
        level = "🟢 منخفض"
    return score, level

def build_report(events):
    grouped = _group_events(events)
    now_utc = datetime.datetime.utcnow().replace(microsecond=0)
    rpt_id = f"RPT-{_now_ksa().strftime('%Y%m%d-%H%M%S')}"

    risk_score, risk_level = _calc_risk_index(grouped)
    highlight = _pick_highlight(grouped)
    main_factor = _extract_main_factor_text(grouped)

    lines = []
    lines.append(REPORT_TITLE)
    lines.append(f"رقم التقرير: {rpt_id}")
    lines.append("الجهة المصدرة: نظام الرصد الآلي – مركز المتابعة")
    lines.append("تصنيف التقرير: تشغيلي – للاستخدام الداخلي")
    lines.append("")
    lines.append("نطاق الرصد: المملكة والدول المجاورة")
    lines.append(f"🕒 تاريخ ووقت التحديث: {now_utc.strftime('%Y-%m-%d %H:%M')} UTC")
    lines.append("⏱️ آلية التحديث: تلقائي")
    lines.append("")
    lines.append("════════════════════")
    lines.append("1️⃣ الملخص التنفيذي")
    lines.append("")
    lines.append(f"📊 مؤشر المخاطر الموحد: {risk_score}/100")
    lines.append(f"📌 مستوى المخاطر: {risk_level}")
    lines.append("")
    lines.append("📌 الحالة العامة: مراقبة")
    lines.append("📈 مقارنة بالفترة السابقة: — (لا توجد مقارنة سابقة)")
    lines.append("")
    lines.append("📍 أبرز حدث خلال آخر 6 ساعات:")
    lines.append(f"{highlight}")
    lines.append("")
    lines.append("🧾 تفسير تشغيلي:")
    lines.append(f"• العامل الرئيسي: {main_factor}")
    if grouped["gdacs"]:
        lines.append("• جي داكس: حدث إقليمي للتوعية — لا يوجد ذكر مباشر للمملكة (تأثير منخفض).")
    lines.append("")
    lines.append("📍 المناطق الأكثر تأثرًا:")
    lines.append("- مدن داخل المملكة")
    lines.append("- الدول المجاورة")
    lines.append("")

    # ===== الأقسام =====
    order = ["food", "gdacs", "fires", "ukmto", "ais"]
    for sec in order:
        hdr = SECTION_HEADERS.get(sec, sec)
        lines.append("════════════════════")
        lines.append(hdr)
        lines.append("")
        sec_lines = _lines_from_titles(grouped.get(sec, []), limit=12)
        # هنا نضيف "- " مرة واحدة فقط
        for s in sec_lines:
            lines.append(f"- {s}")
        lines.append("")

    # ===== ملاحظات =====
    lines.append("════════════════════")
    lines.append("7️⃣ ملاحظات تشغيلية")
    lines.append("")
    lines.append("• تم إعداد التقرير آليًا بناءً على مصادر الرصد المعتمدة.")
    lines.append("• يتم إصدار تنبيه إضافي عند ظهور أحداث جديدة مؤثرة.")

    return "\n".join(lines)

def run(events, force_send=False):
    """
    events: قائمة أحداث بالشكل:
      {"section": "fires|gdacs|ais|ukmto|food", "title": "...", "meta": {...}}
    """
    report = build_report(events)
    state = _load_state()

    h = _sha(report)
    last = state.get("last_hash")

    # منع تكرار نفس التقرير
    if (not force_send) and last == h:
        return report

    _tg_send(report)
    state["last_hash"] = h
    state["last_sent_utc"] = datetime.datetime.utcnow().isoformat() + "Z"
    _save_state(state)
    return report
