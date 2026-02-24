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

    # محاولة خفيفة لتقليل فشل Telegram timeout
    for attempt in range(2):
        try:
            r = requests.post(
                url,
                json={
                    "chat_id": CHAT_ID,
                    "text": text,
                    "disable_web_page_preview": True,
                },
                timeout=40,
            )
            r.raise_for_status()
            return
        except Exception as e:
            if attempt == 1:
                raise
            print(f"[WARN] telegram send failed, retrying: {e}")


def _normalize_section(sec: str) -> str:
    sec = (sec or "other").strip().lower()

    if sec in ["fire", "fires", "firms"]:
        return "fires"
    if sec in ["gdac", "gdacs", "disaster", "disasters"]:
        return "gdacs"
    if sec in ["ukmto", "marine"]:
        return "ukmto"
    if sec in ["ais", "ports", "ships"]:
        return "ais"
    if sec in ["food", "supply", "supply_chain"]:
        return "food"

    return sec


def _group_events(events):
    grouped = {"food": [], "gdacs": [], "fires": [], "ukmto": [], "ais": [], "other": []}
    for e in events or []:
        sec = _normalize_section(e.get("section") or "other")
        if sec not in grouped:
            sec = "other"
        grouped[sec].append(e)
    return grouped


def _lines_from_titles(items, limit=12):
    out = []
    for e in (items or [])[:limit]:
        t = e.get("title") or ""
        t = str(t).strip()
        if t:
            out.append(f"- {t}")
    return out if out else ["- لا يوجد"]


def _top_event(grouped):
    # نختار أبرز حدث: fire داخل السعودية > gdacs > لا يوجد
    if grouped.get("fires"):
        return grouped["fires"][0].get("title") or "🔥 حرائق داخل السعودية"
    if grouped.get("gdacs"):
        return grouped["gdacs"][0].get("title") or "🌍 حدث GDACS"
    return "لا يوجد"


def _risk_score(grouped):
    score = 0
    explain = []

    fires = grouped.get("fires") or []
    gdacs = grouped.get("gdacs") or []

    if fires:
        # افتراض: أول عنصر fires هو "ملخص" من mon_fires
        meta = fires[0].get("meta") or {}
        count = int(meta.get("count") or 0)
        top_frp = float(meta.get("top_frp") or 0)

        if count >= 200 or top_frp >= 80:
            score += 65
            explain.append("• العامل الرئيسي: مؤشرات حرائق/نقاط رصد نشطة داخل المملكة (تأثير مرتفع).")
        elif count >= 50 or top_frp >= 50:
            score += 40
            explain.append("• العامل الرئيسي: مؤشرات حرائق/نقاط رصد نشطة داخل المملكة (للاطلاع).")
        else:
            score += 25
            explain.append("• العامل الرئيسي: مؤشرات حرائق بسيطة داخل المملكة (للاطلاع).")
    else:
        explain.append("• العامل الرئيسي: لا توجد مؤشرات داخل المملكة حالياً.")

    # GDACS فقط للتوعية إذا ما ذكر السعودية (حسب منطقك الحالي)
    if gdacs:
        explain.append("• GDACS: حدث إقليمي للتوعية.")
        score += 10

    # سقف
    if score > 100:
        score = 100

    return score, explain


def _risk_level(score):
    if score >= 80:
        return "🔴 حرج"
    if score >= 60:
        return "🟠 مرتفع"
    if score >= 40:
        return "🟡 مراقبة"
    return "🟢 منخفض"


def _build_report_text(report_title: str, grouped: dict, include_ais: bool):
    now = _now_ksa()
    report_id = f"RPT-{now.strftime('%Y%m%d-%H%M%S')}"

    score, explain = _risk_score(grouped)
    level = _risk_level(score)
    top = _top_event(grouped)

    text = []
    # Header
    text.append(report_title)
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
    text.append("📌 الحالة العامة: مراقبة")
    text.append("📈 مقارنة بالفترة السابقة: — (لا توجد مقارنة سابقة)")
    text.append("")
    text.append("📍 أبرز حدث خلال آخر 6 ساعات:")
    text.append(str(top))
    text.append("")
    text.append("🧾 تفسير تشغيلي:")
    for line in explain:
        text.append(str(line))
    text.append("")
    text.append("📍 المناطق الأكثر تأثرًا:")
    text.append("- مدن داخل المملكة")
    text.append("- الدول المجاورة")
    text.append("")
    text.append("════════════════════")
    text.append("2️⃣ مؤشرات سلاسل الإمداد الغذائي")
    text.append("")
    text.extend(_lines_from_titles(grouped.get("food"), limit=8))
    text.append("")
    text.append("════════════════════")
    text.append("3️⃣ الكوارث الطبيعية")
    text.append("")
    gd_lines = _lines_from_titles(grouped.get("gdacs"), limit=8)
    # لو لا يوجد: خليها عربية أوضح
    if gd_lines == ["- لا يوجد"]:
        gd_lines = ["- لا يوجد أحداث ضمن النطاق حالياً."]
    text.extend(gd_lines)
    text.append("")
    text.append("════════════════════")
    text.append("4️⃣ حرائق الغابات")
    text.append("")
    text.extend(_lines_from_titles(grouped.get("fires"), limit=12))
    text.append("")
    text.append("════════════════════")
    text.append("5️⃣ الأحداث والتحذيرات البحرية")
    text.append("")
    text.extend(_lines_from_titles(grouped.get("ukmto"), limit=8))
    text.append("")
    text.append("════════════════════")
    text.append("6️⃣ حركة السفن وازدحام الموانئ")
    text.append("")
    if include_ais:
        text.extend(_lines_from_titles(grouped.get("ais"), limit=8))
    else:
        text.append("- لا يوجد")
    text.append("")
    text.append("════════════════════")
    text.append("7️⃣ ملاحظات تشغيلية")
    text.append("")
    text.append("• تم إعداد التقرير آليًا بناءً على مصادر الرصد المعتمدة.")
    text.append("• يتم إصدار تنبيه إضافي عند ظهور أحداث جديدة مؤثرة.")

    # تأكد كلها نصوص
    text = [str(x) for x in text]
    return "\n".join(text)


def run(*args, **kwargs):
    """
    يدعم:
      run(events)
      run(events=..., report_title=..., only_if_new=..., include_ais=...)
      run(report_title, events, ...)
    """

    # استخراج بارامترات بشكل مرن
    events = kwargs.get("events", None)
    report_title = kwargs.get("report_title", "📄 تقرير الرصد والتحديث التشغيلي")
    only_if_new = bool(kwargs.get("only_if_new", False))
    include_ais = bool(kwargs.get("include_ais", True))

    # دعم run(events) كأول positional
    if events is None and len(args) >= 1 and isinstance(args[0], list):
        events = args[0]

    # دعم run(title, events)
    if len(args) >= 2 and isinstance(args[0], str) and isinstance(args[1], list):
        report_title = args[0]
        events = args[1]

    if events is None:
        events = []

    grouped = _group_events(events)
    report_text = _build_report_text(report_title, grouped, include_ais)

    # only_if_new logic
    state = _load_state()
    digest = _sha(report_text)
    last = state.get("last_report_sha")

    if only_if_new and last == digest:
        print("[INFO] report unchanged; skipping telegram send")
        return report_text

    _tg_send(report_text)
    state["last_report_sha"] = digest
    _save_state(state)

    return report_text
