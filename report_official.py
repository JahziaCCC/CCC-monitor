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
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    r = requests.post(url, json={
        "chat_id": CHAT_ID,
        "text": text,
        "disable_web_page_preview": True
    }, timeout=45)
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
        t = e.get("title") or ""
        if t.strip():
            out.append(f"- {t.strip()}")
    return out if out else ["- لا يوجد"]


def _pick_top_event(grouped):
    # أولوية: حرائق ثم GDACS ثم AIS ثم UKMTO ثم Food
    for k in ["fires", "gdacs", "ais", "ukmto", "food", "other"]:
        if grouped.get(k):
            t = grouped[k][0].get("title")
            if t:
                return t.strip()
    return "لا يوجد"


def _risk_score(grouped):
    """
    سكور بسيط: حرائق تعطي وزن أعلى، GDACS متوسط، AIS متوسط.
    """
    score = 0

    # Fires
    if grouped["fires"]:
        score += 40
    # GDACS
    if grouped["gdacs"]:
        score += 15
    # AIS
    if grouped["ais"]:
        # إذا في ازدحام عالي (أرقام كبيرة) نرفع
        score += 10
    # UKMTO
    if grouped["ukmto"]:
        score += 10
    # Food
    if grouped["food"]:
        score += 5

    if score > 100:
        score = 100
    return score


def _risk_label(score):
    if score >= 80:
        return "🔴 حرج"
    if score >= 60:
        return "🟠 مرتفع"
    if score >= 40:
        return "🟡 مراقبة"
    return "🟢 منخفض"


def run(events, report_title="📄 تقرير الرصد والتحديث التشغيلي", only_if_new=True):
    now = _now_ksa()
    rid = now.strftime("RPT-%Y%m%d-%H%M%S")
    grouped = _group_events(events)

    score = _risk_score(grouped)
    level = _risk_label(score)

    top = _pick_top_event(grouped)

    # تفسير تشغيلي بسيط
    expl = []
    if grouped["fires"]:
        expl.append("• العامل الرئيسي: مؤشرات حرائق/نقاط رصد نشطة داخل المملكة (تأثير متوسط).")
    if grouped["gdacs"]:
        expl.append("• GDACS: حدث/أحداث ضمن النطاق (للتوعية).")
    if not expl:
        expl.append("• العامل الرئيسي: لا توجد مؤشرات داخل المملكة حالياً.")

    lines = []
    lines.append(report_title)
    lines.append(f"رقم التقرير: {rid}")
    lines.append("الجهة المصدرة: نظام الرصد الآلي – مركز المتابعة")
    lines.append("تصنيف التقرير: تشغيلي – للاستخدام الداخلي")
    lines.append("")
    lines.append("نطاق الرصد: المملكة والدول المجاورة")
    lines.append(f"🕒 تاريخ ووقت التحديث: {now.astimezone(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("⏱️ آلية التحديث: تلقائي")
    lines.append("")
    lines.append("════════════════════")
    lines.append("1️⃣ الملخص التنفيذي")
    lines.append("")
    lines.append(f"📊 مؤشر المخاطر الموحد: {score}/100")
    lines.append(f"📌 مستوى المخاطر: {level}")
    lines.append("")
    lines.append("📍 أبرز حدث خلال آخر 6 ساعات:")
    lines.append(top)
    lines.append("")
    lines.append("🧾 تفسير تشغيلي:")
    lines.extend(expl)
    lines.append("")
    lines.append("════════════════════")
    lines.append("2️⃣ مؤشرات سلاسل الإمداد الغذائي")
    lines.extend(_lines_from_titles(grouped["food"]))
    lines.append("")
    lines.append("════════════════════")
    lines.append("3️⃣ الكوارث الطبيعية")
    lines.extend(_lines_from_titles(grouped["gdacs"]))
    lines.append("")
    lines.append("════════════════════")
    lines.append("4️⃣ حرائق الغابات")
    lines.extend(_lines_from_titles(grouped["fires"], limit=8))
    lines.append("")
    lines.append("════════════════════")
    lines.append("5️⃣ الأحداث والتحذيرات البحرية")
    lines.extend(_lines_from_titles(grouped["ukmto"]))
    lines.append("")
    lines.append("════════════════════")
    lines.append("6️⃣ حركة السفن وازدحام الموانئ")
    lines.extend(_lines_from_titles(grouped["ais"]))
    lines.append("")
    lines.append("════════════════════")
    lines.append("7️⃣ ملاحظات تشغيلية")
    lines.append("• تم إعداد التقرير آليًا بناءً على مصادر الرصد المعتمدة.")
    lines.append("• يتم إصدار تنبيه إضافي عند ظهور أحداث جديدة مؤثرة.")

    text = "\n".join(lines)

    st = _load_state()
    h = _sha(text)
    if only_if_new and st.get("last") == h:
        print("no changes")
        return text

    _tg_send(text)
    st["last"] = h
    _save_state(st)
    return text
