# report_official.py
import os
import json
import hashlib
import datetime
import time
import requests
import re

STATE_FILE = "mewa_state.json"
KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))

BOT = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ========= Helpers =========
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

def _safe_int(x, default=None):
    if x is None:
        return default
    # supports: "3255", "3255.0", "3,255", "3255 µg/m³"
    s = str(x)
    m = re.findall(r"[-+]?\d+(?:\.\d+)?", s.replace(",", ""))
    if not m:
        return default
    try:
        return int(float(m[0]))
    except Exception:
        return default

def _tg_send(text: str, retries=3):
    """
    IMPORTANT:
    - Telegram sometimes times out from GitHub runners.
    - We retry, and if it still fails we DO NOT crash the whole run.
    """
    if not BOT or not CHAT_ID:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

    url = f"https://api.telegram.org/bot{BOT}/sendMessage"

    last_err = None
    for i in range(retries):
        try:
            r = requests.post(
                url,
                json={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True},
                timeout=40,  # أعلى شوي من السابق
            )
            r.raise_for_status()
            return True
        except Exception as e:
            last_err = e
            # backoff
            time.sleep(2 + i * 2)

    # لا نطيّح الـRun بسبب Telegram
    print(f"[WARN] Telegram send failed after retries: {last_err}")
    return False

def _group_events(events):
    grouped = {
        "dust": [],
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

# ========= Risk / Executive logic =========
def _risk_score(grouped):
    """
    Simple scoring (0..100) — adjust if you want later.
    """
    score = 0

    # dust severity: look for any numeric µg/m³
    dust_vals = []
    for e in grouped.get("dust", []):
        v = _safe_int(e.get("value"))
        if v is None:
            # try parse from title
            v = _safe_int(e.get("title"))
        if v is not None:
            dust_vals.append(v)

    if dust_vals:
        mx = max(dust_vals)
        # crude mapping
        if mx >= 2000:
            score += 60
        elif mx >= 1000:
            score += 45
        elif mx >= 500:
            score += 30
        elif mx >= 250:
            score += 20
        elif mx >= 150:
            score += 10

    # fires: add weight if present
    if grouped.get("fires"):
        score += 20

    # gdacs: add awareness weight (small unless Saudi mentioned)
    if grouped.get("gdacs"):
        score += 10

    # maritime / ais (optional small weight)
    if grouped.get("ukmto"):
        score += 10
    if grouped.get("ais"):
        score += 5

    if score > 100:
        score = 100
    return score

def _risk_level(score):
    if score >= 80:
        return "🔴 حرج"
    if score >= 60:
        return "🟠 مرتفع"
    if score >= 35:
        return "🟡 مراقبة"
    return "🟢 منخفض"

def _pick_top_event(grouped):
    """
    ✅ تحسينك اللي اتفقنا عليه:
    - لو GDACS يذكر السعودية/SAUDI/KSA → نخليه أبرز حدث
    - وإلا → أعلى غبار داخل المملكة
    - وإذا ما فيه → "لا يوجد"
    """
    # 1) GDACS mentions Saudi?
    for e in grouped.get("gdacs", []):
        t = (e.get("title") or "").lower()
        if any(k in t for k in ["saudi", "ksa", "السعود", "المملكة", "saudi arabia"]):
            return e.get("title") or "لا يوجد"

    # 2) otherwise highest dust
    best = None
    best_v = None
    for e in grouped.get("dust", []):
        v = _safe_int(e.get("value"))
        if v is None:
            v = _safe_int(e.get("title"))
        if v is None:
            continue
        if best_v is None or v > best_v:
            best_v = v
            best = e

    if best:
        return best.get("title") or "لا يوجد"

    return "لا يوجد"

def _dust_summary_lines(grouped):
    """
    For your 17 locations:
    - if value exists -> show with category
    - else "غير متاح مؤقتاً"
    """
    # Expect each dust event to include: {"location": "...", "value": int or None, "title": "..."}
    # We'll index by location for stable output.
    dust_events = grouped.get("dust", [])
    by_loc = {}
    for e in dust_events:
        loc = e.get("location") or ""
        if loc:
            by_loc[loc] = e

    # Your required list (17)
    LOCS = [
        "الرياض",
        "مكة",
        "المدينة",
        "جدة",
        "المنطقة الشرقية (الدمام)",
        "القصيم (بريدة)",
        "عسير (أبها)",
        "جازان",
        "نجران",
        "الباحة",
        "تبوك",
        "الجوف (سكاكا)",
        "حائل",
        "الحدود الشمالية (عرعر)",
        "القريات",
        "العلا",
        "نيوم",
    ]

    out = []
    missing = 0

    for loc in LOCS:
        e = by_loc.get(loc)
        if not e:
            missing += 1
            out.append(f"- {loc}: غير متاح مؤقتاً")
            continue

        v = _safe_int(e.get("value"))
        if v is None:
            missing += 1
            out.append(f"- {loc}: غير متاح مؤقتاً")
            continue

        # simple labeling
        if v >= 2000:
            out.append(f"- ⚠️ غبار شديد جدًا — {loc}: {v} µg/m³")
        elif v >= 1000:
            out.append(f"- 🌪️ مؤشر غبار مرتفع — {loc}: {v} µg/m³")
        elif v >= 250:
            out.append(f"- 🌪️ مؤشر غبار متوسط — {loc}: {v} µg/m³")
        else:
            out.append(f"- ✅ غبار ضمن الطبيعي — {loc}: {v} µg/m³")

    note = None
    if missing > 0:
        note = f"ℹ️ ملاحظة: تعذر جلب قراءة PM10 لعدد {missing} مواقع (مؤقتاً)."

    return out if out else ["- لا يوجد"], note, len(LOCS)

def build_report_text(events, report_no=None):
    grouped = _group_events(events)

    now_utc = datetime.datetime.utcnow().replace(microsecond=0)
    if not report_no:
        report_no = f"RPT-{now_utc.strftime('%Y%m%d-%H%M%S')}"

    score = _risk_score(grouped)
    level = _risk_level(score)

    top_event = _pick_top_event(grouped)

    dust_lines, dust_note, dust_total = _dust_summary_lines(grouped)

    # Executive dust quick facts for تفسير تشغيلي
    # count cities with values
    dust_vals = []
    for e in grouped.get("dust", []):
        v = _safe_int(e.get("value"))
        if v is not None:
            dust_vals.append((v, e.get("location") or ""))

    dust_vals_sorted = sorted(dust_vals, key=lambda x: x[0], reverse=True)
    dust_cities = len(dust_vals_sorted)
    top_dust_text = ""
    if dust_vals_sorted:
        v, loc = dust_vals_sorted[0]
        top_dust_text = f"{loc} ({v} µg/m³)"

    # GDACS mention Saudi?
    gdacs_saudi = False
    for e in grouped.get("gdacs", []):
        t = (e.get("title") or "").lower()
        if any(k in t for k in ["saudi", "ksa", "السعود", "المملكة", "saudi arabia"]):
            gdacs_saudi = True
            break

    # Build sections
    lines = []
    lines.append("📄 تقرير الرصد والتحديث التشغيلي")
    lines.append(f"رقم التقرير: {report_no}")
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
    lines.append(f"📊 مؤشر المخاطر الموحد: {score}/100")
    lines.append(f"📌 مستوى المخاطر: {level}")
    lines.append("")
    lines.append("📌 الحالة العامة: مراقبة")
    lines.append("📈 مقارنة بالفترة السابقة: — (لا توجد مقارنة سابقة)")
    lines.append("")
    lines.append("📍 أبرز حدث خلال آخر 6 ساعات:")
    lines.append(str(top_event))
    lines.append("")
    lines.append("🧾 تفسير تشغيلي:")
    if dust_cities == 0 and not grouped.get("fires") and not gdacs_saudi:
        lines.append("• العامل الرئيسي: لا توجد مؤشرات داخل المملكة حالياً.")
    else:
        lines.append("• العامل الرئيسي: الغبار داخل المملكة." if dust_cities > 0 else "• العامل الرئيسي: لا يوجد غبار مؤثر داخل المملكة.")
    if dust_cities > 0:
        lines.append(f"• الغبار: {dust_cities} مدن متأثرة — أعلى قراءة: {top_dust_text}")
    if grouped.get("gdacs"):
        if gdacs_saudi:
            lines.append("• GDACS: حدث يذكر المملكة (تأثير أعلى).")
        else:
            lines.append("• GDACS: حدث إقليمي للتوعية — لا يوجد ذكر مباشر للمملكة (تأثير منخفض).")
    lines.append("")
    lines.append("📍 المناطق الأكثر تأثرًا:")
    lines.append("- مدن داخل المملكة")
    lines.append("- الدول المجاورة")
    lines.append("")
    lines.append("════════════════════")
    lines.append("2️⃣ مؤشرات سلاسل الإمداد الغذائي")
    lines.append("")
    # You decided: no dust here unless you implement real food indicators
    food_lines = _lines_from_titles(grouped.get("food", []), limit=8)
    lines.extend(food_lines)
    lines.append("")
    lines.append("════════════════════")
    lines.append("3️⃣ الكوارث الطبيعية (GDACS)")
    lines.append("")
    lines.extend(_lines_from_titles(grouped.get("gdacs", []), limit=10))
    lines.append("")
    lines.append("════════════════════")
    lines.append("4️⃣ حرائق الغابات (FIRMS)")
    lines.append("")
    lines.extend(_lines_from_titles(grouped.get("fires", []), limit=8))
    lines.append("")
    lines.append("════════════════════")
    lines.append("5️⃣ الأحداث والتحذيرات البحرية (UKMTO)")
    lines.append("")
    lines.extend(_lines_from_titles(grouped.get("ukmto", []), limit=8))
    lines.append("")
    lines.append("════════════════════")
    lines.append("6️⃣ حركة السفن وازدحام الموانئ (AIS)")
    lines.append("")
    lines.extend(_lines_from_titles(grouped.get("ais", []), limit=10))
    lines.append("")
    lines.append("════════════════════")
    lines.append("7️⃣ مؤشرات الغبار وجودة الهواء (PM10)")
    lines.append("")
    if dust_lines and dust_lines != ["- لا يوجد"]:
        lines.extend(dust_lines)
    else:
        lines.append("- لا يوجد")
    lines.append("")
    lines.append("════════════════════")
    lines.append("8️⃣ ملاحظات تشغيلية")
    lines.append("")
    if dust_note:
        lines.append(f"• {dust_note}")
    lines.append("• تم إعداد التقرير آليًا بناءً على مصادر الرصد المعتمدة.")
    lines.append("• يتم إصدار تنبيه إضافي عند ظهور أحداث جديدة مؤثرة.")

    return "\n".join(lines)

def send_report(events, only_if_new=False, report_no=None):
    text = build_report_text(events, report_no=report_no)

    state = _load_state()
    key = _sha(text)

    if only_if_new and state.get("last_hash") == key:
        print("[INFO] No changes; skipping Telegram.")
        return False

    ok = _tg_send(text, retries=3)

    # حتى لو فشل Telegram، نحدث الحالة (عشان ما يكرر نفس التقرير بشكل مزعج)
    state["last_hash"] = key
    state["last_report_at_utc"] = datetime.datetime.utcnow().isoformat()
    _save_state(state)

    return ok

# ========= Compatibility entrypoint =========
def run(title="📌 تقرير مجدول", only_if_new=False, include_ais=True, events=None):
    """
    Keep a run() function so your main.py can call report_official.run(...)
    If you pass events explicitly, it will use them.
    """
    if events is None:
        # main.py usually collects events; so if you call run() without events,
        # we just send an empty report.
        events = []
    return send_report(events, only_if_new=only_if_new)
