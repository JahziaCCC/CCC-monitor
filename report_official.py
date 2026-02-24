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

# حدود تنبيه الحرائق (Variables/Env)
def _env_int(name, default):
    try:
        return int(os.environ.get(name, str(default)).strip())
    except Exception:
        return default

ALERT_FIRES_COUNT = _env_int("ALERT_FIRES_COUNT", 200)
ALERT_FIRES_FRP = _env_int("ALERT_FIRES_FRP", 80)
ALERT_FIRES_CLEAR_COUNT = _env_int("ALERT_FIRES_CLEAR_COUNT", 100)
ALERT_FIRES_CLEAR_FRP = _env_int("ALERT_FIRES_CLEAR_FRP", 60)
ALERT_FIRES_COOLDOWN_MIN = _env_int("ALERT_FIRES_COOLDOWN_MIN", 180)


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
            out.append(f"- {t}")
    return out if out else ["- لا يوجد"]

def _extract_fires_summary(fires_events):
    """
    نتوقع أن mon_fires يرسل event فيه title.
    نطلع:
      - count
      - max_frp
      - top points (إن كانت موجودة ضمن titles أو fields)
    """
    count = 0
    max_frp = 0.0

    # لو فيه event واحد ملخّص: "🔥 حرائق نشطة داخل السعودية — 85 رصد..." نقرأ منه
    for e in fires_events or []:
        title = e.get("title") or ""
        m_count = re.search(r"(\d+)\s*رصد", title)
        if m_count:
            try:
                count = max(count, int(m_count.group(1)))
            except Exception:
                pass
        m_frp = re.search(r"FRP[:\s]+(\d+(\.\d+)?)", title)
        if m_frp:
            try:
                max_frp = max(max_frp, float(m_frp.group(1)))
            except Exception:
                pass

    return count, max_frp

def _fire_alert_line(fires_events):
    count, max_frp = _extract_fires_summary(fires_events)
    if count <= 0 and max_frp <= 0:
        return None

    # منطق تنبيه بسيط (PRO): فقط لو تجاوز أحد الحدود
    is_alert = (count >= ALERT_FIRES_COUNT) or (max_frp >= ALERT_FIRES_FRP)
    if not is_alert:
        return None

    return f"🔥 تنبيه حرائق: {count} رصد خلال 24 ساعة | أعلى FRP: {max_frp:.1f}"

def _risk_score(grouped):
    """
    سكّور مبسّط، واقعي، بدون تعقيد:
    - GDACS موجود = +15
    - حرائق موجودة = +10 إلى +40 حسب (count/frp)
    - UKMTO/AIS = +10
    """
    score = 10

    # GDACS
    if grouped["gdacs"]:
        score += 15

    # Fires
    f_count, f_frp = _extract_fires_summary(grouped["fires"])
    if f_count > 0 or f_frp > 0:
        score += 10
        if f_count >= ALERT_FIRES_COUNT or f_frp >= ALERT_FIRES_FRP:
            score += 25
        elif f_count >= ALERT_FIRES_CLEAR_COUNT or f_frp >= ALERT_FIRES_CLEAR_FRP:
            score += 15

    # UKMTO / AIS
    if grouped["ukmto"]:
        score += 10
    if grouped["ais"]:
        score += 10

    # Food
    if grouped["food"]:
        score += 7

    if score < 0:
        score = 0
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

def _pick_top_event(grouped):
    """
    ترتيب الاختيار:
    1) حرائق إذا موجودة
    2) GDACS
    3) UKMTO
    4) AIS
    وإلا: لا يوجد
    """
    if grouped["fires"]:
        # أول سطر من قائمة fires
        t = (grouped["fires"][0].get("title") or "").strip()
        if t:
            return t
    if grouped["gdacs"]:
        t = (grouped["gdacs"][0].get("title") or "").strip()
        if t:
            return t
    if grouped["ukmto"]:
        t = (grouped["ukmto"][0].get("title") or "").strip()
        if t:
            return t
    if grouped["ais"]:
        t = (grouped["ais"][0].get("title") or "").strip()
        if t:
            return t
    return "لا يوجد"

def _build_report_text(report_title, grouped, include_ais=True):
    now = _now_ksa()
    report_id = f"RPT-{now.strftime('%Y%m%d-%H%M%S')}"
    utc_now = datetime.datetime.now(datetime.timezone.utc)

    score = _risk_score(grouped)
    level = _risk_label(score)

    top_event = _pick_top_event(grouped)

    # تفسير تشغيلي مختصر
    explain = []
    fires_line = _fire_alert_line(grouped["fires"])
    if fires_line:
        explain.append(f"• {fires_line}")

    if grouped["fires"]:
        explain.append("• العامل الرئيسي: مؤشرات حرائق/نقاط رصد نشطة داخل المملكة (للاطلاع).")
    else:
        explain.append("• العامل الرئيسي: لا توجد مؤشرات داخل المملكة حالياً.")

    if grouped["gdacs"]:
        explain.append("• GDACS: حدث إقليمي للتوعية.")
    else:
        explain.append("• GDACS: لا يوجد.")

    explain_block = "\n".join(explain)

    # أقسام
    food_lines = _lines_from_titles(grouped["food"])
    gdacs_lines = _lines_from_titles(grouped["gdacs"])
    fires_lines = _lines_from_titles(grouped["fires"])
    ukmto_lines = _lines_from_titles(grouped["ukmto"])
    ais_lines = _lines_from_titles(grouped["ais"]) if include_ais else ["- (تم إيقاف AIS)"]

    text = []
    text.append(f"{report_title}")
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
    text.append(f"{top_event}\n")
    text.append("🧾 تفسير تشغيلي:")
    text.append(explain_block + "\n")
    text.append("📍 المناطق الأكثر تأثرًا:")
    text.append("- مدن داخل المملكة")
    text.append("- الدول المجاورة\n")

    text.append("════════════════════")
    text.append("2️⃣ مؤشرات سلاسل الإمداد الغذائي\n")
    text.extend(food_lines)
    text.append("")

    text.append("════════════════════")
    text.append("3️⃣ الكوارث الطبيعية (GDACS)\n")
    text.extend(gdacs_lines)
    text.append("")

    text.append("════════════════════")
    text.append("4️⃣ حرائق الغابات (FIRMS)\n")
    text.extend(fires_lines)
    text.append("")

    text.append("════════════════════")
    text.append("5️⃣ الأحداث والتحذيرات البحرية (UKMTO)\n")
    text.extend(ukmto_lines)
    text.append("")

    text.append("════════════════════")
    text.append("6️⃣ حركة السفن وازدحام الموانئ (AIS)\n")
    text.extend(ais_lines)
    text.append("")

    text.append("════════════════════")
    text.append("7️⃣ ملاحظات تشغيلية\n")
    text.append("• تم إعداد التقرير آليًا بناءً على مصادر الرصد المعتمدة.")
    text.append("• يتم إصدار تنبيه إضافي عند ظهور أحداث جديدة مؤثرة.")
    return "\n".join(text)

def run(
    report_title="📄 تقرير الرصد والتحديث التشغيلي",
    only_if_new=True,
    include_ais=True,
    events=None
):
    grouped = _group_events(events or [])
    report_text = _build_report_text(report_title, grouped, include_ais=include_ais)

    state = _load_state()
    key = "ccc_report_hash"
    new_hash = _sha(report_text)

    if only_if_new and state.get(key) == new_hash:
        # لا يوجد تغيير
        return False

    # حفظ قبل الإرسال (حتى لو تعطل تيليجرام ما يكرر بشكل مزعج)
    state[key] = new_hash
    state["ccc_report_last_sent"] = _now_ksa().isoformat()
    _save_state(state)

    _tg_send(report_text)
    return True
