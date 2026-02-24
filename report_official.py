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


# ======================
# تنسيق الأسطر (حل مشكلة - -)
# ======================

def _lines_from_titles(items, limit=12):
    out = []

    for e in items[:limit]:
        t = (e.get("title") or "").strip()
        if not t:
            continue

        # إزالة الشرطة إذا كانت موجودة مسبقاً
        t = t.lstrip("-").strip()

        out.append(f"- {t}")

    return out if out else ["- لا يوجد"]


# ======================
# تحليل حرائق
# ======================

def _extract_fires_summary(fires_events):
    count = 0
    max_frp = 0.0

    for e in fires_events or []:
        title = e.get("title") or ""

        m_count = re.search(r"(\d+)\s*رصد", title)
        if m_count:
            try:
                count = max(count, int(m_count.group(1)))
            except:
                pass

        m_frp = re.search(r"FRP[:\s]+(\d+(\.\d+)?)", title)
        if m_frp:
            try:
                max_frp = max(max_frp, float(m_frp.group(1)))
            except:
                pass

    return count, max_frp


# ======================
# حساب المخاطر
# ======================

def _risk_score(grouped):
    score = 10

    if grouped["gdacs"]:
        score += 15

    f_count, f_frp = _extract_fires_summary(grouped["fires"])
    if f_count > 0 or f_frp > 0:
        score += 15

    if grouped["ukmto"]:
        score += 10

    if grouped["ais"]:
        score += 10

    if grouped["food"]:
        score += 5

    return min(100, score)


def _risk_label(score):
    if score >= 80:
        return "🔴 حرج"
    if score >= 60:
        return "🟠 مرتفع"
    if score >= 40:
        return "🟡 مراقبة"
    return "🟢 منخفض"


def _pick_top_event(grouped):
    if grouped["fires"]:
        return grouped["fires"][0].get("title", "لا يوجد")
    if grouped["gdacs"]:
        return grouped["gdacs"][0].get("title", "لا يوجد")
    return "لا يوجد"


# ======================
# بناء التقرير
# ======================

def _build_report_text(report_title, grouped, include_ais=True):

    now = _now_ksa()
    report_id = f"RPT-{now.strftime('%Y%m%d-%H%M%S')}"
    utc_now = datetime.datetime.now(datetime.timezone.utc)

    score = _risk_score(grouped)
    level = _risk_label(score)
    top_event = _pick_top_event(grouped)

    f_count, f_frp = _extract_fires_summary(grouped["fires"])

    explain = []

    if f_count > 0 or f_frp > 0:
        explain.append("• العامل الرئيسي: مؤشرات حرائق/نقاط رصد نشطة داخل المملكة (للاطلاع).")
    else:
        explain.append("• العامل الرئيسي: لا توجد مؤشرات داخل المملكة حالياً.")

    if grouped["gdacs"]:
        explain.append("• GDACS: حدث إقليمي للتوعية.")

    explain_block = "\n".join(explain)

    text = []
    text.append(report_title)
    text.append(f"رقم التقرير: {report_id}")
    text.append("الجهة المصدرة: نظام الرصد الآلي – مركز المتابعة")
    text.append("تصنيف التقرير: تشغيلي – للاستخدام الداخلي\n")
    text.append("نطاق الرصد: المملكة والدول المجاورة")
    text.append(f"🕒 تاريخ ووقت التحديث: {utc_now.strftime('%Y-%m-%d %H:%M')} UTC")
    text.append("⏱️ آلية التحديث: تلقائي\n")

    text.append("════════════════════")
    text.append("1️⃣ الملخص التنفيذي\n")
    text.append(f"📊 مؤشر المخاطر الموحد: {score}/100")
    text.append(f"📌 مستوى المخاطر: {level}\n")
    text.append("📌 الحالة العامة: مراقبة")
    text.append("📈 مقارنة بالفترة السابقة: — (لا توجد مقارنة سابقة)\n")
    text.append("📍 أبرز حدث خلال آخر 6 ساعات:")
    text.append(top_event + "\n")
    text.append("🧾 تفسير تشغيلي:")
    text.append(explain_block + "\n")
    text.append("📍 المناطق الأكثر تأثرًا:")
    text.append("- مدن داخل المملكة")
    text.append("- الدول المجاورة\n")

    text.append("════════════════════")
    text.append("2️⃣ مؤشرات سلاسل الإمداد الغذائي\n")
    text.extend(_lines_from_titles(grouped["food"]))
    text.append("")

    text.append("════════════════════")
    text.append("3️⃣ الكوارث الطبيعية (GDACS)\n")
    text.extend(_lines_from_titles(grouped["gdacs"]))
    text.append("")

    text.append("════════════════════")
    text.append("4️⃣ حرائق الغابات (FIRMS)\n")
    text.extend(_lines_from_titles(grouped["fires"]))
    text.append("")

    text.append("════════════════════")
    text.append("5️⃣ الأحداث والتحذيرات البحرية (UKMTO)\n")
    text.extend(_lines_from_titles(grouped["ukmto"]))
    text.append("")

    text.append("════════════════════")
    text.append("6️⃣ حركة السفن وازدحام الموانئ (AIS)\n")
    if include_ais:
        text.extend(_lines_from_titles(grouped["ais"]))
    else:
        text.append("- (تم إيقاف AIS)")
    text.append("")

    text.append("════════════════════")
    text.append("7️⃣ ملاحظات تشغيلية\n")
    text.append("• تم إعداد التقرير آليًا بناءً على مصادر الرصد المعتمدة.")
    text.append("• يتم إصدار تنبيه إضافي عند ظهور أحداث جديدة مؤثرة.")

    return "\n".join(text)


# ======================
# التشغيل الرئيسي
# ======================

def run(
    report_title="📄 تقرير الرصد والتحديث التشغيلي",
    only_if_new=True,
    include_ais=True,
    events=None
):

    grouped = _group_events(events or [])
    report_text = _build_report_text(report_title, grouped, include_ais)

    state = _load_state()
    new_hash = _sha(report_text)

    if only_if_new and state.get("last_hash") == new_hash:
        return False

    _tg_send(report_text)

    state["last_hash"] = new_hash
    _save_state(state)

    return True
