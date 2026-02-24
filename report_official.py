# report_official.py
import os
import json
import hashlib
import datetime
import requests
import html

STATE_FILE = "mewa_state.json"
KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))

BOT = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# الدول المجاورة/ذات الأولوية (تعديلها إذا تبغى)
NEARBY_KEYWORDS = [
    "Saudi", "Saudi Arabia", "KSA", "Kingdom of Saudi Arabia", "المملكة", "السعودية",
    "UAE", "United Arab Emirates", "الإمارات",
    "Qatar", "قطر",
    "Bahrain", "البحرين",
    "Kuwait", "الكويت",
    "Oman", "عمان",
    "Yemen", "اليمن",
    "Jordan", "الأردن",
    "Iraq", "العراق",
    "Syria", "سوريا",
    "Iran", "إيران",
    "Türkiye", "Turkey", "تركيا",
    "Lebanon", "لبنان",
    "Palestine", "فلسطين",
    "Gulf", "الخليج",
    "Red Sea", "البحر الأحمر"
]


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
    if not BOT or not CHAT_ID:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    r = requests.post(url, json={
        "chat_id": CHAT_ID,
        "text": text,
        "disable_web_page_preview": True
    }, timeout=40)
    r.raise_for_status()


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
        t = t.lstrip("- ").strip()  # يمنع - - لا يوجد
        out.append(f"- {t}")
    return out if out else ["- لا يوجد"]


# ======================
# GDACS: filter + Arabic + cleanup
# ======================

def _gdacs_is_nearby(line: str) -> bool:
    s = (line or "").lower()
    for kw in NEARBY_KEYWORDS:
        if kw.lower() in s:
            return True
    return False


def _translate_gdacs(line: str) -> str:
    # فك HTML مثل &amp;
    line = html.unescape(line or "")

    # تعريب + تحسينات
    repl = {
        "earthquake": "زلزال",
        "flood alert": "تنبيه فيضانات",
        "flood": "فيضانات",
        "drought": "جفاف",
        "storm": "عاصفة",

        "Magnitude": "القوة",
        "Depth": "العمق",
        "km": "كم",

        "Few people affected": "تأثير محدود على السكان",
        "people affected": "متأثرون",
        "in MMI": "ضمن مؤشر شدة الاهتزاز (MMI)",

        "Green": "🟢 منخفض",
        "Orange": "🟠 متوسط",
        "Red": "🔴 مرتفع",

        " in ": " في ",
        " alert in ": " في ",
        " South Of ": " جنوب ",
        " Islands": " الجزر",
        "United States": "الولايات المتحدة",
        "Democratic Republic of Congo": "جمهورية الكونغو الديمقراطية",
        "Chile": "تشيلي",
        "Indonesia": "إندونيسيا",
        "Philippines": "الفلبين",
        "Russia": "روسيا",
    }

    for k, v in repl.items():
        line = line.replace(k, v)

    return line.strip()


def _gdacs_lines_filtered(items, limit=8):
    # نفلتر أولاً بناءً على القرب (السعودية + جوارها)
    filtered = []
    for e in (items or []):
        t = str(e.get("title", "")).strip()
        if not t:
            continue
        t = t.lstrip("- ").strip()
        if _gdacs_is_nearby(t):
            filtered.append({"title": t})

    # إذا ما فيه شيء ضمن النطاق: "لا يوجد"
    if not filtered:
        return ["- لا يوجد"]

    # نرجع خطوط مترجمة ونظيفة
    out = []
    for line in _lines(filtered, limit=limit):
        # line أصلاً يبدأ بـ "- "
        core = line[2:].strip()
        core = _translate_gdacs(core)
        out.append(f"- {core}")
    return out


# ======================
# RISK SCORE
# ======================

def _risk(grouped):
    fires = grouped["fires"]
    gdacs = grouped["gdacs"]

    score = 0
    explain = []

    # الحرائق
    if fires:
        meta = fires[0].get("meta", {}) or {}
        count = int(meta.get("count", 0))
        frp = float(meta.get("top_frp", 0))

        # تبسيط منطقي: عدد كبير = مرتفع، متوسط = مراقبة
        if count >= 200 or frp >= 80:
            score += 55
            explain.append("• العامل الرئيسي: مؤشرات حرائق/نقاط رصد نشطة داخل المملكة (تأثير مرتفع).")
        elif count >= 50 or frp >= 40:
            score += 40
            explain.append("• العامل الرئيسي: مؤشرات حرائق/نقاط رصد نشطة داخل المملكة (تأثير متوسط).")
        else:
            score += 20
            explain.append("• العامل الرئيسي: مؤشرات حرائق محدودة داخل المملكة (تأثير منخفض).")
    else:
        explain.append("• العامل الرئيسي: لا توجد مؤشرات داخل المملكة حالياً.")

    # GDACS (بعد الفلترة)
    gdacs_near = any(_gdacs_is_nearby(str(e.get("title", ""))) for e in (gdacs or []))
    if gdacs_near:
        explain.append("• GDACS: حدث ضمن النطاق (للتوعية).")
        score += 5
    else:
        # لا نضيف سكور لو GDACS بعيد
        pass

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

    # أبرز حدث: أولاً حرائق داخل المملكة، ثم GDACS (ضمن النطاق فقط)
    top = "لا يوجد"
    if grouped["fires"]:
        top = grouped["fires"][0].get("title", "لا يوجد")
    else:
        # اختار أول GDACS قريب
        for e in grouped["gdacs"]:
            t = str(e.get("title", "")).strip()
            if t and _gdacs_is_nearby(t):
                top = _translate_gdacs(t)
                break

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
    text.extend(_gdacs_lines_filtered(grouped["gdacs"], limit=8))

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
# RUN
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
