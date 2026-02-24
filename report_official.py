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

# ===== Helpers =====
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
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "disable_web_page_preview": True
    }

    # retries بسيطة لتجاوز ReadTimeout في GitHub Actions
    last_err = None
    for _ in range(3):
        try:
            r = requests.post(url, json=payload, timeout=45)
            r.raise_for_status()
            return
        except Exception as e:
            last_err = e
    raise last_err

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
    for e in (items or [])[:limit]:
        t = (e.get("title") or "").strip()
        if t:
            out.append(f"- {t}")
    return out if out else ["- لا يوجد"]

def _safe_int(x, default=0):
    try:
        return int(float(x))
    except Exception:
        return default

def _extract_fires_summary(fires_items):
    """
    يقرأ count/frp من أول عنصر summary لو موجود.
    falls back: يحسب عدد العناصر كـ count إذا ما فيه summary.
    """
    if not fires_items:
        return 0, 0.0

    # لو عندنا summary event
    for e in fires_items:
        if (e.get("kind") or "").lower() == "summary":
            count = _safe_int(e.get("count"), 0)
            frp = float(e.get("max_frp") or 0.0)
            return count, frp

    # otherwise
    return len(fires_items), 0.0

def _risk_score(grouped):
    """
    سكّور بسيط يعتمد على:
    - حرائق (count/max_frp)
    - GDACS ذكر السعودية
    """
    score = 0

    f_count, f_frp = _extract_fires_summary(grouped.get("fires"))
    if f_count >= 200 or f_frp >= 80:
        score += 50
    elif f_count >= 100 or f_frp >= 60:
        score += 25
    elif f_count > 0:
        score += 10

    # GDACS: إذا ذكر السعودية نرفع
    gd_ksa = any((e.get("ksa_related") is True) for e in grouped.get("gdacs", []))
    if gd_ksa:
        score += 25
    else:
        # حدث إقليمي للتوعية (منخفض)
        if grouped.get("gdacs"):
            score += 5

    if score > 100:
        score = 100

    # مستوى المخاطر
    if score >= 80:
        level = "🔴 حرج"
    elif score >= 60:
        level = "🟠 مرتفع"
    elif score >= 40:
        level = "🟡 مراقبة"
    else:
        level = "🟢 منخفض"

    return score, level

def _pick_highlight(grouped):
    """
    في التقرير الرئيسي (بدون غبار):
    - إذا GDACS يذكر السعودية -> خذ GDACS
    - وإلا إذا فيه حرائق (count/frp>0) -> خذ حرائق summary
    - وإلا -> لا يوجد
    """
    gdacs_ksa = [e for e in grouped.get("gdacs", []) if e.get("ksa_related") is True]
    if gdacs_ksa:
        return gdacs_ksa[0].get("title") or "حدث GDACS"

    f_count, f_frp = _extract_fires_summary(grouped.get("fires"))
    if (f_count > 0) or (f_frp > 0):
        # ابحث عن summary title إن وجدت
        for e in grouped.get("fires", []):
            if (e.get("kind") or "").lower() == "summary" and (e.get("title") or "").strip():
                return e["title"].strip()
        return f"🔥 حرائق نشطة داخل السعودية — {f_count} رصد خلال آخر 24 ساعة (أعلى FRP: {f_frp})"

    return "لا يوجد"

def _build_report_text(report_id: str, now_utc: datetime.datetime, events):
    grouped = _group_events(events)
    score, level = _risk_score(grouped)
    highlight = _pick_highlight(grouped)

    # تفسير تشغيلي (يُصلح مشكلة “العامل الرئيسي”)
    explain = []
    f_count, f_frp = _extract_fires_summary(grouped.get("fires"))
    if f_count > 0 or f_frp > 0:
        explain.append("• العامل الرئيسي: مؤشرات حرائق/نقاط رصد نشطة داخل المملكة (للاطلاع).")
    else:
        explain.append("• العامل الرئيسي: لا توجد مؤشرات داخل المملكة حالياً.")

    if grouped.get("gdacs"):
        # إذا ما فيه ذكر مباشر للمملكة نذكر أنها للتوعية
        gd_ksa = any((e.get("ksa_related") is True) for e in grouped["gdacs"])
        if gd_ksa:
            explain.append("• GDACS: حدث طبيعي يذكر المملكة (يتطلب متابعة).")
        else:
            explain.append("• GDACS: حدث إقليمي للتوعية — لا يوجد ذكر مباشر للمملكة (تأثير منخفض).")

    # مناطق متأثرة (بسيطة)
    affected = []
    if f_count > 0:
        affected.append("- مدن داخل المملكة")
    if grouped.get("gdacs"):
        affected.append("- الدول المجاورة")
    if not affected:
        affected = ["- مدن داخل المملكة", "- الدول المجاورة"]

    lines = []
    lines.append("📄 تقرير الرصد والتحديث التشغيلي")
    lines.append(f"رقم التقرير: {report_id}")
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
    lines.append(highlight if highlight.startswith(("🌍", "🔥", "⚠️", "🌪️")) else f"{highlight}")
    lines.append("")
    lines.append("🧾 تفسير تشغيلي:")
    lines.extend(explain)
    lines.append("")
    lines.append("📍 المناطق الأكثر تأثرًا:")
    lines.extend(affected)
    lines.append("")
    lines.append("════════════════════")
    lines.append("2️⃣ مؤشرات سلاسل الإمداد الغذائي")
    lines.append("")
    lines.extend(_lines_from_titles(grouped.get("food"), limit=6))
    lines.append("")
    lines.append("════════════════════")
    lines.append("3️⃣ الكوارث الطبيعية (GDACS)")
    lines.append("")
    lines.extend(_lines_from_titles(grouped.get("gdacs"), limit=6))
    lines.append("")
    lines.append("════════════════════")
    lines.append("4️⃣ حرائق الغابات (FIRMS)")
    lines.append("")
    lines.extend(_lines_from_titles(grouped.get("fires"), limit=10))
    lines.append("")
    lines.append("════════════════════")
    lines.append("5️⃣ الأحداث والتحذيرات البحرية (UKMTO)")
    lines.append("")
    lines.extend(_lines_from_titles(grouped.get("ukmto"), limit=8))
    lines.append("")
    lines.append("════════════════════")
    lines.append("6️⃣ حركة السفن وازدحام الموانئ (AIS)")
    lines.append("")
    lines.extend(_lines_from_titles(grouped.get("ais"), limit=12))
    lines.append("")
    lines.append("════════════════════")
    lines.append("7️⃣ ملاحظات تشغيلية")
    lines.append("")
    lines.append("• تم إعداد التقرير آليًا بناءً على مصادر الرصد المعتمدة.")
    lines.append("• يتم إصدار تنبيه إضافي عند ظهور أحداث جديدة مؤثرة.")

    return "\n".join(lines)

# ===== Public API =====
def run(report_title: str, events=None, only_if_new: bool = False, include_ais: bool = True):
    """
    signature ثابت عشان main.py ما يكسر
    - report_title: عنوان/اسم داخلي
    - events: قائمة events جاهزة
    - only_if_new: لو True لن يرسل إذا نفس النص سابقاً
    """
    now_utc = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
    report_id = f"RPT-{now_utc.strftime('%Y%m%d-%H%M%S')}"
    text = _build_report_text(report_id, now_utc, events or [])

    state = _load_state()
    last_hash = state.get("last_report_hash", "")

    h = _sha(text)
    if only_if_new and h == last_hash:
        return {"sent": False, "reason": "no_change", "report_id": report_id}

    _tg_send(text)
    state["last_report_hash"] = h
    state["last_report_id"] = report_id
    state["last_report_ts_utc"] = now_utc.strftime("%Y-%m-%d %H:%M:%S")
    _save_state(state)
    return {"sent": True, "report_id": report_id}
