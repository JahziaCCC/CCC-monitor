# report_official.py (NO AIR/PM10)
import os
import json
import hashlib
import datetime
import time
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

def _tg_send(text: str, retries=3):
    if not BOT or not CHAT_ID:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    last_err = None

    for i in range(retries):
        try:
            r = requests.post(
                url,
                json={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True},
                timeout=40,
            )
            r.raise_for_status()
            return True
        except Exception as e:
            last_err = e
            time.sleep(2 + i * 2)

    print(f"[WARN] Telegram send failed after retries: {last_err}")
    return False

def _group_events(events):
    grouped = {
        "food": [],
        "gdacs": [],
        "fires": [],
        "ukmto": [],
        "ais": [],
        "other": [],
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

def _risk_score(grouped):
    score = 0
    if grouped.get("fires"):
        score += 25
    if grouped.get("gdacs"):
        score += 15
    if grouped.get("ukmto"):
        score += 10
    if grouped.get("ais"):
        score += 5
    if grouped.get("food"):
        score += 8
    return min(score, 100)

def _risk_level(score):
    if score >= 80:
        return "🔴 حرج"
    if score >= 60:
        return "🟠 مرتفع"
    if score >= 35:
        return "🟡 مراقبة"
    return "🟢 منخفض"

def _pick_highlight(grouped):
    for e in grouped.get("gdacs", []):
        t = (e.get("title") or "").lower()
        if any(k in t for k in ["saudi", "ksa", "السعود", "المملكة", "saudi arabia"]):
            return e.get("title") or "لا يوجد"
    if grouped.get("fires"):
        return grouped["fires"][0].get("title") or "لا يوجد"
    if grouped.get("gdacs"):
        return grouped["gdacs"][0].get("title") or "لا يوجد"
    if grouped.get("ukmto"):
        return grouped["ukmto"][0].get("title") or "لا يوجد"
    if grouped.get("ais"):
        return grouped["ais"][0].get("title") or "لا يوجد"
    return "لا يوجد"

def build_report_text(title: str, events: list):
    grouped = _group_events(events)
    now = _now_ksa()
    report_id = f"RPT-{now.strftime('%Y%m%d-%H%M%S')}"
    scope = "المملكة والدول المجاورة"

    score = _risk_score(grouped)
    level = _risk_level(score)
    highlight = _pick_highlight(grouped)

    gdacs_saudi = any(
        any(k in (e.get("title") or "").lower() for k in ["saudi", "ksa", "السعود", "المملكة", "saudi arabia"])
        for e in grouped.get("gdacs", [])
    )

    txt = []
    txt.append("📄 تقرير الرصد والتحديث التشغيلي")
    txt.append(f"رقم التقرير: {report_id}")
    txt.append("الجهة المصدرة: نظام الرصد الآلي – مركز المتابعة")
    txt.append("تصنيف التقرير: تشغيلي – للاستخدام الداخلي\n")
    txt.append(f"نطاق الرصد: {scope}")
    txt.append(f"🕒 تاريخ ووقت التحديث: {now.astimezone(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
    txt.append("⏱️ آلية التحديث: تلقائي\n")

    txt.append("════════════════════")
    txt.append("1️⃣ الملخص التنفيذي\n")
    txt.append(f"📊 مؤشر المخاطر الموحد: {score}/100")
    txt.append(f"📌 مستوى المخاطر: {level}\n")
    txt.append("📌 الحالة العامة: مراقبة")
    txt.append("📈 مقارنة بالفترة السابقة: — (لا توجد مقارنة سابقة)\n")
    txt.append("📍 أبرز حدث خلال آخر 6 ساعات:")
    txt.append(f"{highlight}\n")

    txt.append("🧾 تفسير تشغيلي:")
    if grouped.get("fires"):
        txt.append("• العامل الرئيسي: مؤشرات حرائق/نقاط رصد نشطة داخل المملكة (للاطلاع).")
    else:
        txt.append("• العامل الرئيسي: لا توجد مؤشرات تشغيلية داخل المملكة حالياً (حسب المصادر الحالية).")

    if grouped.get("gdacs"):
        if gdacs_saudi:
            txt.append("• GDACS: يوجد ذكر مباشر للمملكة (تأثير محتمل).")
        else:
            txt.append("• GDACS: حدث إقليمي للتوعية — لا يوجد ذكر مباشر للمملكة (تأثير منخفض).")

    txt.append("\n📍 المناطق الأكثر تأثرًا:")
    txt.append("- مدن داخل المملكة")
    txt.append("- الدول المجاورة\n")

    txt.append("════════════════════")
    txt.append("2️⃣ مؤشرات سلاسل الإمداد الغذائي\n")
    txt.extend(_lines_from_titles(grouped.get("food", []), limit=8))

    txt.append("\n════════════════════")
    txt.append("3️⃣ الكوارث الطبيعية (GDACS)\n")
    txt.extend(_lines_from_titles(grouped.get("gdacs", []), limit=10))

    txt.append("\n════════════════════")
    txt.append("4️⃣ حرائق الغابات (FIRMS)\n")
    txt.extend(_lines_from_titles(grouped.get("fires", []), limit=8))

    txt.append("\n════════════════════")
    txt.append("5️⃣ الأحداث والتحذيرات البحرية (UKMTO)\n")
    txt.extend(_lines_from_titles(grouped.get("ukmto", []), limit=8))

    txt.append("\n════════════════════")
    txt.append("6️⃣ حركة السفن وازدحام الموانئ (AIS)\n")
    txt.extend(_lines_from_titles(grouped.get("ais", []), limit=10))

    txt.append("\n════════════════════")
    txt.append("7️⃣ ملاحظات تشغيلية\n")
    txt.append("• تم إعداد التقرير آليًا بناءً على مصادر الرصد المعتمدة.")
    txt.append("• يتم إصدار تنبيه إضافي عند ظهور أحداث جديدة مؤثرة.")

    return "\n".join(txt)

def run(title="📌 تقرير مجدول", only_if_new=False, include_ais=True, events=None):
    if events is None:
        events = []

    text = build_report_text(title=title, events=events)
    state = _load_state()
    h = _sha(text)

    if only_if_new and state.get("last_hash") == h:
        print("[INFO] No changes; skipping Telegram.")
        return False

    ok = _tg_send(text, retries=3)
    state["last_hash"] = h
    state["last_report_at_utc"] = datetime.datetime.utcnow().isoformat()
    _save_state(state)
    return ok
