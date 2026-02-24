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
        "pm10_list": [],   # ✅ جديد
        "ops_note": [],
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

_NUM_RE = re.compile(r"(\d[\d\s,.\u00A0\u2009\u202F\u066B\u066C]*\d|\d)")

def _parse_best_int(text: str):
    if not text:
        return None
    matches = _NUM_RE.findall(text)
    nums = []
    for m in matches:
        cleaned = (
            m.replace(",", "")
             .replace(".", "")
             .replace("\u066C", "")
             .replace("\u066B", "")
             .replace("\u00A0", "")
             .replace("\u2009", "")
             .replace("\u202F", "")
             .replace(" ", "")
        )
        if cleaned.isdigit():
            try:
                nums.append(int(cleaned))
            except Exception:
                pass
    return max(nums) if nums else None

def _extract_top_dust(dust_items):
    best = None
    for e in dust_items:
        t = e.get("title", "")
        v = _parse_best_int(t)
        if v is not None:
            if best is None or v > best[0]:
                best = (v, t)
    return best

def _risk_score(grouped):
    score = 0

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

    for e in grouped["gdacs"]:
        t = (e.get("title") or "").lower()
        if "red" in t:
            score += 35
        elif "orange" in t:
            score += 22
        elif "yellow" in t:
            score += 10

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

    if any((e.get("title") or "").strip() for e in grouped["ukmto"]):
        score += 18

    if any((e.get("title") or "").strip() for e in grouped["ais"]):
        score += 10

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
    # ✅ 1) لو GDACS يذكر السعودية -> خذه
    for e in grouped["gdacs"]:
        t = e.get("title") or ""
        if ("Saudi" in t) or ("السعودية" in t) or ("KSA" in t):
            return t

    # ✅ 2) لو عندنا غبار مرتفع داخل المملكة -> خذه
    top = _extract_top_dust(grouped["dust"])
    if top:
        return top[1]

    # ✅ 3) لو لا يوجد مؤشرات داخل المملكة لكن فيه GDACS -> خله أبرز حدث كتوعية
    if grouped["gdacs"]:
        return grouped["gdacs"][0].get("title") or "لا يوجد"

    # ✅ 4) باقي المصادر
    for k in ["fires", "ukmto", "ais"]:
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

    # ✅ قسم PM10: نطبع القائمة التي أتت من mon_dust مهما كانت
    txt.append("\n════════════════════")
    txt.append("7️⃣ مؤشرات الغبار وجودة الهواء (PM10)\n")
    pm10_lines = []
    for obj in grouped["pm10_list"]:
        pm10_lines.extend(obj.get("pm10_lines") or [])
    if pm10_lines:
        txt.extend(pm10_lines)
    else:
        txt.append("- لا يوجد")

    txt.append("\n════════════════════")
    txt.append("8️⃣ ملاحظات تشغيلية\n")
    for e in grouped["ops_note"]:
        t = (e.get("title") or "").strip()
        if t:
            txt.append(f"• {t}")
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
