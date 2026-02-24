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


# ======================
# أدوات أساسية
# ======================

def _now_ksa():
    return datetime.datetime.now(tz=KSA_TZ)


def _load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _tg_send(text):
    if not BOT or not CHAT_ID:
        print("Telegram disabled")
        return

    url = f"https://api.telegram.org/bot{BOT}/sendMessage"

    try:
        requests.post(
            url,
            json={
                "chat_id": CHAT_ID,
                "text": text,
                "disable_web_page_preview": True
            },
            timeout=30
        )
    except Exception as e:
        print("Telegram error:", e)


# ======================
# تجميع الأحداث
# ======================

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


def _lines_from_titles(items, limit=10):
    out = []
    for e in items[:limit]:
        t = e.get("title", "").strip()
        if t:
            out.append(f"- {t}")
    return out if out else ["- لا يوجد"]


# ======================
# بناء التقرير
# ======================

def build_report_text(events):

    grouped = _group_events(events)

    now = _now_ksa().strftime("%Y-%m-%d %H:%M UTC")

    report = []
    report.append("📄 تقرير الرصد والتحديث التشغيلي")
    report.append(f"🕒 تاريخ ووقت التحديث: {now}")
    report.append("")
    report.append("════════════════════")
    report.append("1️⃣ الملخص التنفيذي")
    report.append("")

    # أبرز حدث
    top_event = "لا يوجد"
    if grouped["fires"]:
        top_event = grouped["fires"][0].get("title", "لا يوجد")
    elif grouped["gdacs"]:
        top_event = grouped["gdacs"][0].get("title", "لا يوجد")

    report.append(f"📍 أبرز حدث خلال آخر 6 ساعات:")
    report.append(top_event)
    report.append("")

    # تفسير تشغيلي
    report.append("🧾 تفسير تشغيلي:")
    if grouped["fires"]:
        report.append("• العامل الرئيسي: مؤشرات حرائق/نقاط رصد نشطة داخل المملكة (للاطلاع).")
    else:
        report.append("• العامل الرئيسي: لا توجد مؤشرات داخل المملكة حالياً.")

    if grouped["gdacs"]:
        report.append("• GDACS: حدث إقليمي للتوعية — لا يوجد ذكر مباشر للمملكة (تأثير منخفض).")

    report.append("")
    report.append("════════════════════")
    report.append("2️⃣ مؤشرات سلاسل الإمداد الغذائي")
    report += _lines_from_titles(grouped["food"])
    report.append("")

    report.append("════════════════════")
    report.append("3️⃣ الكوارث الطبيعية")
    report += _lines_from_titles(grouped["gdacs"])
    report.append("")

    report.append("════════════════════")
    report.append("4️⃣ حرائق الغابات (FIRMS)")
    report += _lines_from_titles(grouped["fires"])
    report.append("")

    report.append("════════════════════")
    report.append("5️⃣ الأحداث والتحذيرات البحرية (UKMTO)")
    report += _lines_from_titles(grouped["ukmto"])
    report.append("")

    report.append("════════════════════")
    report.append("6️⃣ حركة السفن وازدحام الموانئ (AIS)")
    report += _lines_from_titles(grouped["ais"])
    report.append("")

    report.append("════════════════════")
    report.append("7️⃣ ملاحظات تشغيلية")
    report.append("• تم إعداد التقرير آليًا بناءً على مصادر الرصد المعتمدة.")
    report.append("• يتم إصدار تنبيه إضافي عند ظهور أحداث جديدة مؤثرة.")

    return "\n".join(report)


# ======================
# التشغيل الرئيسي
# ======================

def run(report_title="CCC Monitor", events=None):

    text = build_report_text(events or [])

    state = _load_state()
    new_hash = _sha(text)

    if state.get("last_hash") == new_hash:
        print("No changes")
        return

    _tg_send(text)

    state["last_hash"] = new_hash
    _save_state(state)

    print("Report sent successfully")
