# report_official.py
import os
import json
import hashlib
import datetime
import requests

STATE_FILE = "mewa_state.json"
KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))

BOT = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


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
    # إذا ما فيه توكن/شات آي دي لا يفشل التشغيل
    if not BOT or not CHAT_ID:
        print("ℹ️ Telegram غير مفعّل (لا يوجد TELEGRAM_BOT_TOKEN أو TELEGRAM_CHAT_ID).")
        return

    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    r = requests.post(
        url,
        json={
            "chat_id": CHAT_ID,
            "text": text,
            "disable_web_page_preview": True
        },
        timeout=30
    )
    r.raise_for_status()


def _group_events(events):
    """
    يجمع الأحداث حسب section.
    كل event لازم يكون dict مثل:
    {"section": "fires", "title": "...", ...}
    """
    grouped = {
        "dust": [],
        "food": [],
        "gdacs": [],
        "fires": [],
        "ukmto": [],
        "ais": [],
        "other": []
    }

    for e in (events or []):
        if not isinstance(e, dict):
            continue
        sec = (e.get("section") or "other").strip().lower()
        if sec not in grouped:
            sec = "other"
        grouped[sec].append(e)

    return grouped


def _lines_from_titles(items, limit=12):
    out = []
    for e in (items or [])[:limit]:
        t = (e.get("title") or "").strip()
        if t:
            # تأكد أنه سطر نصي فقط
            out.append(f"- {t}")
    return out if out else ["- لا يوجد"]


def _pick_top_event(grouped):
    """
    يرجع أفضل حدث للعرض في الملخص التنفيذي.
    الأولوية: fires ثم gdacs ثم ukmto ثم ais ثم food ثم dust
    """
    priority = ["fires", "gdacs", "ukmto", "ais", "food", "dust", "other"]
    for k in priority:
        if grouped.get(k):
            t = (grouped[k][0].get("title") or "").strip()
            if t:
                return t
    return "لا يوجد"


def _build_report_text(report_title, grouped, include_ais=True):
    now = _now_ksa().strftime("%Y-%m-%d %H:%M KSA")

    top_event = _pick_top_event(grouped)

    # مؤشر مبسط (تقدر تعدله لاحقاً)
    # إذا فيه fires أو gdacs نخليها مراقبة/مرتفع، غير ذلك منخفض
    risk_score = 0
    if grouped.get("fires"):
        risk_score = max(risk_score, 55)
    if grouped.get("gdacs"):
        risk_score = max(risk_score, 30)
    if grouped.get("ukmto"):
        risk_score = max(risk_score, 35)
    if include_ais and grouped.get("ais"):
        risk_score = max(risk_score, 25)

    if risk_score >= 70:
        risk_level = "🟠 مرتفع"
    elif risk_score >= 40:
        risk_level = "🟡 مراقبة"
    else:
        risk_level = "🟢 منخفض"

    text = []
    text.append(f"{report_title}")
    text.append(f"🕒 تاريخ ووقت التحديث: {now}")
    text.append("")
    text.append("════════════════════")
    text.append("1️⃣ الملخص التنفيذي")
    text.append("")
    text.append(f"📊 مؤشر المخاطر الموحد: {risk_score}/100")
    text.append(f"📌 مستوى المخاطر: {risk_level}")
    text.append("")
    text.append("📍 أبرز حدث خلال آخر 6 ساعات:")
    text.append(f"{top_event}")
    text.append("")
    text.append("🧾 تفسير تشغيلي:")
    if grouped.get("fires"):
        text.append("• العامل الرئيسي: مؤشرات حرائق/نقاط رصد نشطة داخل المملكة (للاطلاع).")
    else:
        text.append("• العامل الرئيسي: لا توجد مؤشرات حرائق داخل المملكة حالياً.")
    if grouped.get("gdacs"):
        text.append("• GDACS: حدث/أحداث ضمن النطاق (للتوعية).")
    text.append("")
    text.append("════════════════════")
    text.append("2️⃣ مؤشرات سلاسل الإمداد الغذائي")
    text.extend(_lines_from_titles(grouped.get("food")))
    text.append("")
    text.append("════════════════════")
    text.append("3️⃣ الكوارث الطبيعية")
    text.extend(_lines_from_titles(grouped.get("gdacs")))
    text.append("")
    text.append("════════════════════")
    text.append("4️⃣ حرائق الغابات")
    text.extend(_lines_from_titles(grouped.get("fires"), limit=30))
    text.append("")
    text.append("════════════════════")
    text.append("5️⃣ الأحداث والتحذيرات البحرية")
    text.extend(_lines_from_titles(grouped.get("ukmto")))
    text.append("")
    text.append("════════════════════")
    text.append("6️⃣ حركة السفن وازدحام الموانئ")
    if include_ais:
        text.extend(_lines_from_titles(grouped.get("ais")))
    else:
        text.append("- لا يوجد")
    text.append("")
    text.append("════════════════════")
    text.append("7️⃣ ملاحظات تشغيلية")
    text.append("• تم إعداد التقرير آليًا بناءً على مصادر الرصد المعتمدة.")
    text.append("• يتم إصدار تنبيه إضافي عند ظهور أحداث جديدة مؤثرة.")

    return "\n".join(text)


def run(
    report_title="📄 تقرير الرصد والتحديث التشغيلي",
    report_id=None,
    only_if_new=False,
    include_ais=True,
    events=None,
):
    """
    Compatible with main.py:
    report_official.run(
        report_title=...,
        report_id=...,
        only_if_new=...,
        include_ais=...,
        events=...
    )
    """
    if events is None:
        events = []

    grouped = _group_events(events)
    report_text = _build_report_text(report_title, grouped, include_ais=include_ais)

    # طباعة للتأكد داخل Actions
    print(report_text)

    # منع الإرسال إذا ما فيه تغيير (اختياري)
    if only_if_new and report_id:
        state = _load_state()
        new_hash = _sha(report_text)
        old_hash = state.get(report_id)
        if old_hash == new_hash:
            print("ℹ️ لا يوجد تغيير في التقرير (only_if_new=True) — تم تجاوز الإرسال.")
            return report_text
        state[report_id] = new_hash
        _save_state(state)

    # إرسال تيليجرام بدون ما يكسر التشغيل لو فشل
    try:
        _tg_send(report_text)
    except Exception as e:
        print(f"⚠️ فشل إرسال Telegram (لن نوقف التشغيل): {e}")

    return report_text
