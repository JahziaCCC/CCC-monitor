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
        "dust": [],
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

# ✅ استخراج رقم قوي جداً (يدعم 3,255 و 3٬255 و 3 255 و 3255 و 2719)
_NUM_RE = re.compile(r"(\d[\d\s,.\u00A0\u2009\u202F\u066B\u066C]*\d|\d)")

def _parse_best_int(text: str):
    """
    يأخذ نص ويستخرج أكبر رقم صحيح منه حتى لو كان بصيغ مختلفة.
    """
    if not text:
        return None
    matches = _NUM_RE.findall(text)
    nums = []
    for m in matches:
        # إزالة كل الفواصل والمسافات الخاصة
        cleaned = (
            m.replace(",", "")
             .replace(".", "")
             .replace("\u066C", "")  # Arabic thousands separator (٬)
             .replace("\u066B", "")  # Arabic decimal separator (٫)
             .replace("\u00A0", "")  # NBSP
             .replace("\u2009", "")  # thin space
             .replace("\u202F", "")  # narrow no-break space
             .replace(" ", "")
        )
        if cleaned.isdigit():
            try:
                nums.append(int(cleaned))
            except Exception:
                pass
    return max(nums) if nums else None

def _extract_top_dust(dust_items):
    """
    يرجع أعلى قراءة غبار من عناوين مثل:
    "🌪️ مؤشر غبار مرتفع — الرياض: 3,255 µg/m³"
    """
    best = None  # (value, title)
    for e in dust_items:
        t = e.get("title", "")
        v = _parse_best_int(t)
        if v is not None:
            if best is None or v > best[0]:
                best = (v, t)
    return best

def _risk_score(grouped):
    score = 0

    # Dust
    top = _extract_top_dust(grouped["dust"])
    if top:
        v = top[0]
        if v >= 2500:
            score += 35
        elif v >= 1500:
            score += 25
        elif v >= 600:
            score += 15
        elif v >= 300:
            score += 8

    # GDACS
    for e in grouped["gdacs"]:
        t = (e.get("title") or "").lower()
        if "red" in t:
            score += 35
        elif "orange" in t:
            score += 22
        elif "yellow" in t:
            score += 10

    # Fires
    if grouped["fires"]:
        c = 0
        for e in grouped["fires"]:
            try:
                c = max(c, int(e.get("count") or 0))
            except Exception:
                pass
        if c >= 100:
            score += 25
        elif c >= 20:
            score += 18
        elif c >= 1:
            score += 10
        else:
            score += 5

    # UKMTO
    if any((e.get("title") or "").strip() for e in grouped["ukmto"]):
        score += 18

    # AIS
    if any((e.get("title") or "").strip() for e in grouped["ais"]):
        score += 10

    # Food
    if any((e.get("title") or "").strip() for e in grouped["food"]):
        score += 8

    return min(score, 100)

def _risk_level(score: int):
    if score >= 80:
        return "🔴 حرج"
    if score >= 60:
        return "🟠 مرتفع"
    if score >= 35:
        return "🟡 مراقبة"
    return "🟢 منخفض"

def _pick_highlight(grouped):
    # لو GDACS يذكر السعودية -> GDACS، وإلا أعلى غبار داخل المملكة
    for e in grouped["gdacs"]:
        t = e.get("title") or ""
        if ("Saudi" in t) or ("السعودية" in t) or ("KSA" in t):
            return t

    top = _extract_top_dust(grouped["dust"])
    if top:
        return top[1]

    for k in ["fires", "ukmto", "ais", "gdacs", "dust"]:
        if grouped[k]:
            return grouped[k][0].get("title") or "لا يوجد"
    return "لا يوجد"

def build_report_text(title: str, events: list):
    grouped = _group_events(events)
    now = _now_ksa()
    report_id = f"RPT-{now.strftime('%Y%m%d')}-{now.strftime('%H%M%S')}"
    scope = "المملكة والدول المجاورة"

    score = _risk_score(grouped)
    level = _risk_level(score)
    highlight = _pick_highlight(grouped)

    top = _extract_top_dust(grouped["dust"])
    dust_count = len([e for e in grouped["dust"] if (e.get("title") or "").strip()])
    gdacs_mentions_ksa = any(
        ("Saudi" in (e.get("title") or "")) or ("السعودية" in (e.get("title") or "")) or ("KSA" in (e.get("title") or ""))
        for e in grouped["gdacs"]
    )

    txt = []
    txt.append(f"{title}")
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
    if top:
        txt.append("• العامل الرئيسي: الغبار داخل المملكة.")
        txt.append(f"• الغبار: {dust_count} مدن متأثرة — أعلى قراءة: {top[1]}")
    else:
        txt.append("• العامل الرئيسي: لا توجد مؤشرات داخل المملكة حالياً.")
    if gdacs_mentions_ksa:
        txt.append("• GDACS: يوجد ذكر مباشر للمملكة (تأثير محتمل).")
    else:
        txt.append("• GDACS: حدث إقليمي للتوعية — لا يوجد ذكر مباشر للمملكة (تأثير منخفض).")

    txt.append("\n📍 المناطق الأكثر تأثرًا:")
    txt.append("- مدن داخل المملكة")
    txt.append("- الدول المجاورة\n")

    txt.append("════════════════════")
    txt.append("2️⃣ مؤشرات سلاسل الإمداد الغذائي\n")
    txt.extend(_lines_from_titles(grouped["food"], limit=6))

    txt.append("\n════════════════════")
    txt.append("3️⃣ الكوارث الطبيعية (GDACS)\n")
    txt.extend(_lines_from_titles(grouped["gdacs"], limit=8))

    txt.append("\n════════════════════")
    txt.append("4️⃣ حرائق الغابات (FIRMS)\n")
    txt.extend(_lines_from_titles(grouped["fires"], limit=8))

    txt.append("\n════════════════════")
    txt.append("5️⃣ الأحداث والتحذيرات البحرية (UKMTO)\n")
    txt.extend(_lines_from_titles(grouped["ukmto"], limit=6))

    txt.append("\n════════════════════")
    txt.append("6️⃣ حركة السفن وازدحام الموانئ (AIS)\n")
    txt.extend(_lines_from_titles(grouped["ais"], limit=10))

    txt.append("\n════════════════════")
    txt.append("7️⃣ مؤشرات الغبار وجودة الهواء (PM10)\n")
    txt.extend(_lines_from_titles(grouped["dust"], limit=13))

    txt.append("\n════════════════════")
    txt.append("8️⃣ ملاحظات تشغيلية\n")
    txt.append("• تم إعداد التقرير آليًا بناءً على مصادر الرصد المعتمدة.")
    txt.append("• يتم إصدار تنبيه إضافي عند ظهور أحداث جديدة مؤثرة.")

    return "\n".join(txt)

def run(title: str, events: list, only_if_new: bool = False):
    text = build_report_text(title=title, events=events)

    if only_if_new:
        st = _load_state()
        h = _sha(text)
        if st.get("last_hash") == h:
            return
        st["last_hash"] = h
        _save_state(st)

    _tg_send(text)
