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
# HELPERS
# ======================

def _now():
    return datetime.datetime.now(tz=KSA_TZ)


def _load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def _save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _sha(txt):
    return hashlib.sha256(txt.encode("utf-8")).hexdigest()


def _tg_send(text):
    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    requests.post(url, json={
        "chat_id": CHAT_ID,
        "text": text,
        "disable_web_page_preview": True
    }, timeout=40)


# ======================
# GROUPING
# ======================

def _group(events):
    g = {
        "food": [],
        "gdacs": [],
        "fires": [],
        "ukmto": [],
        "ais": [],
        "other": []
    }

    for e in events or []:
        sec = (e.get("section") or "other").lower()
        if sec not in g:
            sec = "other"
        g[sec].append(e)

    return g


# ======================
# CLEAN LIST LINES
# ======================

def _lines(items, limit=10):
    out = []

    for e in (items or [])[:limit]:
        t = str(e.get("title", "")).strip()

        if not t:
            continue

        # منع - - لا يوجد
        t = t.lstrip("- ").strip()

        out.append(f"- {t}")

    return out if out else ["- لا يوجد"]


# ======================
# GDACS ARABIC
# ======================

def _translate_gdacs(line):

    repl = {
        "earthquake": "زلزال",
        "flood": "فيضانات",
        "drought": "جفاف",
        "storm": "عاصفة",
        "Green": "🟢 منخفض",
        "Orange": "🟠 متوسط",
        "Red": "🔴 مرتفع"
    }

    for k, v in repl.items():
        line = line.replace(k, v)

    return line


# ======================
# RISK SCORE (مخفف)
# ======================

def _risk(grouped):

    fires = grouped["fires"]
    gdacs = grouped["gdacs"]

    score = 0
    explain = []

    if fires:
        meta = fires[0].get("meta", {})
        count = int(meta.get("count", 0))
        frp = float(meta.get("top_frp", 0))

        if count >= 200:
            score += 50
            explain.append("• العامل الرئيسي: مؤشرات حرائق/نقاط رصد نشطة داخل المملكة (تأثير مرتفع).")
        elif count >= 50:
            score += 35
            explain.append("• العامل الرئيسي: مؤشرات حرائق/نقاط رصد نشطة داخل المملكة (للاطلاع).")
        else:
            score += 20
            explain.append("• العامل الرئيسي: مؤشرات حرائق بسيطة داخل المملكة.")

    else:
        explain.append("• العامل الرئيسي: لا توجد مؤشرات داخل المملكة حالياً.")

    if gdacs:
        explain.append("• GDACS: حدث إقليمي للتوعية.")
        score += 5

    return min(score, 100), explain


def _risk_level(score):
    if score >= 80:
        return "🔴 حرج"
    if score >= 60:
        return "🟠 مرتفع"
    if score >= 40:
        return "🟡 مراقبة"
    return "🟢 منخفض"


# ======================
# BUILD REPORT
# ======================

def _build(title, grouped, include_ais=True):

    now = _now()
    report_id = now.strftime("RPT-%Y%m%d-%H%M%S")

    score, explain = _risk(grouped)
    level = _risk_level(score)

    top = "لا يوجد"
    if grouped["fires"]:
        top = grouped["fires"][0]["title"]
    elif grouped["gdacs"]:
        top = grouped["gdacs"][0]["title"]

    text = []

    text.append(title)
    text.append(f"رقم التقرير: {report_id}")
    text.append("الجهة المصدرة: نظام الرصد الآلي – مركز المتابعة")
    text.append("تصنيف التقرير: تشغيلي – للاستخدام الداخلي")
    text.append("")
    text.append("نطاق الرصد: المملكة والدول المجاورة")
    text.append(f"🕒 تاريخ ووقت التحديث: {now.astimezone(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    text.append("⏱️ آلية التحديث: تلقائي")
    text.append("")
    text.append("════════════════════")
    text.append("1️⃣ الملخص التنفيذي")
    text.append("")
    text.append(f"📊 مؤشر المخاطر الموحد: {score}/100")
    text.append(f"📌 مستوى المخاطر: {level}")
    text.append("")
    text.append("📍 أبرز حدث خلال آخر 6 ساعات:")
    text.append(top)
    text.append("")
    text.append("🧾 تفسير تشغيلي:")
    text.extend(explain)

    text.append("")
    text.append("════════════════════")
    text.append("2️⃣ مؤشرات سلاسل الإمداد الغذائي")
    text.extend(_lines(grouped["food"]))

    text.append("")
    text.append("════════════════════")
    text.append("3️⃣ الكوارث الطبيعية")

    gd = [_translate_gdacs(x) for x in _lines(grouped["gdacs"])]
    text.extend(gd)

    text.append("")
    text.append("════════════════════")
    text.append("4️⃣ حرائق الغابات")
    text.extend(_lines(grouped["fires"], 12))

    text.append("")
    text.append("════════════════════")
    text.append("5️⃣ الأحداث والتحذيرات البحرية")
    text.extend(_lines(grouped["ukmto"]))

    text.append("")
    text.append("════════════════════")
    text.append("6️⃣ حركة السفن وازدحام الموانئ")
    text.extend(_lines(grouped["ais"] if include_ais else []))

    text.append("")
    text.append("════════════════════")
    text.append("7️⃣ ملاحظات تشغيلية")
    text.append("• تم إعداد التقرير آليًا بناءً على مصادر الرصد المعتمدة.")
    text.append("• يتم إصدار تنبيه إضافي عند ظهور أحداث جديدة مؤثرة.")

    return "\n".join([str(x) for x in text])


# ======================
# RUN (متوافق مع كل نسخ main.py)
# ======================

def run(events=None, report_title="📄 تقرير الرصد والتحديث التشغيلي",
        only_if_new=False, include_ais=True):

    events = events or []

    grouped = _group(events)

    report = _build(report_title, grouped, include_ais)

    state = _load_state()
    h = _sha(report)

    if only_if_new and state.get("last") == h:
        print("no changes")
        return report

    _tg_send(report)

    state["last"] = h
    _save_state(state)

    return report
