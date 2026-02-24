# report_official.py
import os
import json
import hashlib
import datetime
import requests
import re
from typing import List, Dict

STATE_FILE = "mewa_state.json"
KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))

BOT = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()


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
    r = requests.post(
        url,
        json={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True},
        timeout=30,
    )
    r.raise_for_status()


def _group_events(events: List[Dict]) -> Dict[str, List[Dict]]:
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


def _lines(items: List[Dict], limit=12) -> List[str]:
    out = []
    for e in (items or [])[:limit]:
        t = (e.get("title") or "").strip()
        if t:
            # تأكد ما يطلع "- -"
            if t.startswith("- "):
                out.append(t)
            else:
                out.append(f"- {t}")
    return out if out else ["- لا يوجد"]


def _fires_stats(grouped: Dict[str, List[Dict]]):
    """
    يرجع (count, max_frp) لو موجود سطر 🔥 وإلا (0,0)
    """
    fires = grouped.get("fires") or []
    for e in fires:
        t = (e.get("title") or "").strip()
        if t.startswith("🔥"):
            m = re.search(r"—\s*(\d+)\s*رصد", t)
            m2 = re.search(r"أعلى\s*FRP:\s*([0-9.]+)", t)
            count = int(m.group(1)) if m else 0
            max_frp = float(m2.group(1)) if m2 else 0.0
            return count, max_frp
    return 0, 0.0


def _gdacs_has_events(grouped):
    gd = grouped.get("gdacs") or []
    # إذا فيه أي عنصر مو "لا يوجد" اعتبر فيه أحداث
    for e in gd:
        t = (e.get("title") or "").strip()
        if t and "لا يوجد" not in t:
            return True
    return False


def _risk_score(grouped):
    """
    سكور بسيط: حرائق + (GDACS كمعلومة)
    أنت تقدر توسّعه لاحقاً.
    """
    score = 0

    fires_count, fires_frp = _fires_stats(grouped)

    if fires_count == 0:
        fires_score = 0
    else:
        alert_count = int(os.environ.get("ALERT_FIRES_COUNT", "200"))
        alert_frp = float(os.environ.get("ALERT_FIRES_FRP", "80"))

        # قاعدة بسيطة
        fires_score = 25  # وجود حرائق = أساس
        if fires_count >= alert_count:
            fires_score += 25
        if fires_frp >= alert_frp:
            fires_score += 25

    score += fires_score

    # GDACS: للتوعية فقط (0..10)
    if _gdacs_has_events(grouped):
        score += 5

    return max(0, min(100, score))


def _risk_level(score: int):
    if score >= 80:
        return "🔴 حرج"
    if score >= 60:
        return "🟠 مرتفع"
    if score >= 40:
        return "🟡 مراقبة"
    return "🟢 منخفض"


def _main_event_6h(grouped):
    """
    يختار أبرز حدث (هنا نفضّل الحرائق ثم GDACS)
    """
    fires = grouped.get("fires") or []
    for e in fires:
        t = (e.get("title") or "").strip()
        if t.startswith("🔥"):
            return t

    gd = grouped.get("gdacs") or []
    for e in gd:
        t = (e.get("title") or "").strip()
        if t and "لا يوجد" not in t:
            return t

    return "لا يوجد"


def _impact_for_fires(fires_count, fires_frp):
    if fires_count == 0:
        return None
    alert_count = int(os.environ.get("ALERT_FIRES_COUNT", "200"))
    alert_frp = float(os.environ.get("ALERT_FIRES_FRP", "80"))

    if fires_count >= alert_count or fires_frp >= alert_frp:
        return "مرتفع"
    if fires_count >= 50:
        return "متوسط"
    return "منخفض"


def _build_report_text(report_title: str, report_id: str, grouped: Dict[str, List[Dict]], include_ais: bool):
    now = _now_ksa()

    score = _risk_score(grouped)
    level = _risk_level(score)
    main_event = _main_event_6h(grouped)

    fires_count, fires_frp = _fires_stats(grouped)
    fires_impact = _impact_for_fires(fires_count, fires_frp)

    lines = []
    lines.append(report_title)
    lines.append(f"رقم التقرير: {report_id}")
    lines.append("الجهة المصدرة: نظام الرصد الآلي – مركز المتابعة")
    lines.append("تصنيف التقرير: تشغيلي – للاستخدام الداخلي")
    lines.append("")
    lines.append("نطاق الرصد: المملكة والدول المجاورة")
    lines.append(f"🕒 تاريخ ووقت التحديث: {now.strftime('%Y-%m-%d %H:%M')} KSA")
    lines.append("⏱️ آلية التحديث: تلقائي")
    lines.append("")
    lines.append("════════════════════")
    lines.append("1️⃣ الملخص التنفيذي")
    lines.append("")
    lines.append(f"📊 مؤشر المخاطر الموحد: {score}/100")
    lines.append(f"📌 مستوى المخاطر: {level}")
    lines.append("")
    lines.append("📍 أبرز حدث خلال آخر 6 ساعات:")
    lines.append(main_event)
    lines.append("")
    lines.append("🧾 تفسير تشغيلي:")

    if fires_count == 0:
        lines.append("• العامل الرئيسي: لا توجد مؤشرات حرائق داخل المملكة حالياً.")
    else:
        lines.append(f"• العامل الرئيسي: مؤشرات حرائق/نقاط رصد نشطة داخل المملكة (تأثير {fires_impact}).")

    # GDACS شرح بسيط
    if _gdacs_has_events(grouped):
        lines.append("• GDACS: حدث/أحداث ضمن النطاق (للتوعية).")
    else:
        lines.append("• GDACS: لا يوجد أحداث ضمن النطاق حالياً.")

    lines.append("")
    lines.append("════════════════════")
    lines.append("2️⃣ مؤشرات سلاسل الإمداد الغذائي")
    lines.extend(_lines(grouped.get("food"), limit=12))
    lines.append("")
    lines.append("════════════════════")
    lines.append("3️⃣ الكوارث الطبيعية")
    lines.extend(_lines(grouped.get("gdacs"), limit=12))
    lines.append("")
    lines.append("════════════════════")
    lines.append("4️⃣ حرائق الغابات")
    lines.extend(_lines(grouped.get("fires"), limit=12))
    lines.append("")
    lines.append("════════════════════")
    lines.append("5️⃣ الأحداث والتحذيرات البحرية")
    lines.extend(_lines(grouped.get("ukmto"), limit=12))
    lines.append("")
    lines.append("════════════════════")
    lines.append("6️⃣ حركة السفن وازدحام الموانئ")
    if include_ais:
        lines.extend(_lines(grouped.get("ais"), limit=12))
    else:
        lines.append("- ℹ️ AIS مستبعد من التقرير.")
    lines.append("")
    lines.append("════════════════════")
    lines.append("7️⃣ ملاحظات تشغيلية")
    lines.append("• تم إعداد التقرير آليًا بناءً على مصادر الرصد المعتمدة.")
    lines.append("• يتم إصدار تنبيه إضافي عند ظهور أحداث جديدة مؤثرة.")

    # مهم: join نص فقط
    return "\n".join(lines)


def run(
    report_title: str = "📄 تقرير الرصد والتحديث التشغيلي",
    report_id: str = "",
    events: List[Dict] = None,
    include_ais: bool = True,
    only_if_new: bool = True,
    **kwargs
):
    grouped = _group_events(events or [])
    if not report_id:
        now = _now_ksa()
        report_id = f"RPT-{now.strftime('%Y%m%d-%H%M%S')}"

    report_text = _build_report_text(report_title, report_id, grouped, include_ais=include_ais)

    # Dedup (اختياري)
    state = _load_state()
    h = _sha(report_text)

    if only_if_new and state.get("last_hash") == h:
        # لا ترسل نفس التقرير مرتين
        return

    # إرسال تيليجرام (لا نكسر لو فشل)
    try:
        _tg_send(report_text)
    except Exception as e:
        # احفظ ملاحظة محلية فقط
        state["last_send_error"] = f"{type(e).__name__}"
        _save_state(state)
        raise

    state["last_hash"] = h
    state["last_sent_at"] = _now_ksa().isoformat()
    _save_state(state)
