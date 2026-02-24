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
    if not BOT or not CHAT_ID:
        # لو تبي تمنع الكراش وقت التجربة
        return
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

def _lines(items, limit=12):
    out = []
    for e in (items or [])[:limit]:
        t = (e.get("title") or "").strip()
        if t:
            out.append(f"- {t}")
    return out if out else ["- لا يوجد"]

def _risk_score(grouped):
    # منطق مبسط: ارفع المخاطر حسب الحرائق
    fires = grouped.get("fires", [])
    score = 0

    # لو فيه عنوان ملخص حرائق يبدأ بـ 🔥 اعتبره مؤشر
    has_fire = any((e.get("title","").startswith("🔥")) for e in fires)
    if has_fire:
        score += 55
    else:
        score += 0

    # GDACS إذا فيه رسالة فقط ما يرفع كثير
    if grouped.get("gdacs"):
        score += 5

    return max(0, min(100, score))

def _risk_level(score):
    if score >= 80:
        return "🔴 حرج"
    if score >= 60:
        return "🟠 مرتفع"
    if score >= 40:
        return "🟡 مراقبة"
    return "🟢 منخفض"

def _build_report_text(report_no, ts_utc, grouped):
    score = _risk_score(grouped)
    level = _risk_level(score)

    # أبرز حدث
    highlight = "لا يوجد"
    if grouped["fires"]:
        # أول سطر حرائق غالباً هو الملخص
        highlight = (grouped["fires"][0].get("title") or "لا يوجد")

    text = []
    text.append("📄 تقرير الرصد والتحديث التشغيلي")
    text.append(f"رقم التقرير: {report_no}")
    text.append("الجهة المصدرة: نظام الرصد الآلي – مركز المتابعة")
    text.append("تصنيف التقرير: تشغيلي – للاستخدام الداخلي")
    text.append("")
    text.append("نطاق الرصد: المملكة والدول المجاورة")
    text.append(f"🕒 تاريخ ووقت التحديث: {ts_utc} UTC")
    text.append("⏱️ آلية التحديث: تلقائي")
    text.append("")
    text.append("════════════════════")
    text.append("1️⃣ الملخص التنفيذي")
    text.append("")
    text.append(f"📊 مؤشر المخاطر الموحد: {score}/100")
    text.append(f"📌 مستوى المخاطر: {level}")
    text.append("")
    text.append("📍 أبرز حدث خلال آخر 6 ساعات:")
    text.append(f"{highlight}")
    text.append("")
    text.append("🧾 تفسير تشغيلي:")
    if grouped["fires"]:
        text.append("• العامل الرئيسي: مؤشرات حرائق/نقاط رصد نشطة داخل المملكة (تأثير متوسط).")
    else:
        text.append("• العامل الرئيسي: لا توجد مؤشرات داخل المملكة حالياً.")
    if grouped["gdacs"]:
        text.append("• GDACS: حدث/أحداث ضمن النطاق (للتوعية).")
    text.append("")
    text.append("════════════════════")
    text.append("2️⃣ مؤشرات سلاسل الإمداد الغذائي")
    text.extend(_lines(grouped["food"]))
    text.append("")
    text.append("════════════════════")
    text.append("3️⃣ الكوارث الطبيعية")
    text.extend(_lines(grouped["gdacs"]))
    text.append("")
    text.append("════════════════════")
    text.append("4️⃣ حرائق الغابات")
    text.extend(_lines(grouped["fires"], limit=20))
    text.append("")
    text.append("════════════════════")
    text.append("5️⃣ الأحداث والتحذيرات البحرية")
    text.extend(_lines(grouped["ukmto"]))
    text.append("")
    text.append("════════════════════")
    text.append("6️⃣ حركة السفن وازدحام الموانئ")
    text.extend(_lines(grouped["ais"]))
    text.append("")
    text.append("════════════════════")
    text.append("7️⃣ ملاحظات تشغيلية")
    text.append("• تم إعداد التقرير آليًا بناءً على مصادر الرصد المعتمدة.")
    text.append("• يتم إصدار تنبيه إضافي عند ظهور أحداث جديدة مؤثرة.")

    return "\n".join(text)

def run(events):
    now = _now_ksa()
    ts_utc = now.astimezone(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
    report_no = f"RPT-{now.astimezone(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    grouped = _group_events(events)

    report_text = _build_report_text(report_no, ts_utc, grouped)

    # منع تكرار نفس التقرير
    state = _load_state()
    h = _sha(report_text)
    if state.get("last_hash") == h:
        return report_text

    _tg_send(report_text)
    state["last_hash"] = h
    _save_state(state)
    return report_text
