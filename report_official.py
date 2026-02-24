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
    # لا تفشل التشغيل لو تيليجرام غير مفعّل
    if not BOT or not CHAT_ID:
        print("ℹ️ Telegram غير مفعّل (لا يوجد TELEGRAM_BOT_TOKEN أو TELEGRAM_CHAT_ID).")
        return

    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    r = requests.post(
        url,
        json={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True},
        timeout=30,
    )
    r.raise_for_status()


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
    for e in (events or []):
        if not isinstance(e, dict):
            continue
        sec = (e.get("section") or "other").strip().lower()
        if sec not in grouped:
            sec = "other"
        grouped[sec].append(e)
    return grouped


def _arabize_gdacs_title(title: str) -> str:
    """
    يحوّل سطور GDACS إلى عربي قدر الإمكان بدون ما يعتمد على ترجمة خارجية.
    مثال:
    Green earthquake (Magnitude 5.5M, Depth:10km) in Indonesia 24/02/2026 07:46 UTC, Few people affected ...
    =>
    🟢 منخفض زلزال (قوة 5.5M، عمق 10km) في Indonesia بتاريخ 24/02/2026 07:46 UTC، تأثر محدود ...
    """
    t = (title or "").strip()
    if not t:
        return t

    # إزالة تكرار Green/Orange/Red من بداية النص إذا كان موجود
    # ونحوله لأيقونة عربية
    level_map = {
        "green": "🟢 منخفض",
        "orange": "🟠 مرتفع",
        "red": "🔴 حرج",
        "yellow": "🟡 مراقبة",
    }

    # التقط مستوى اللون إن وجد
    m = re.match(r"^(GDACS\s+)?(Green|Orange|Red|Yellow)\b\s*[-—:]*\s*", t, flags=re.I)
    prefix = ""
    if m:
        color = m.group(2).lower()
        prefix = level_map.get(color, "")
        t = t[m.end():].strip()

    # مصطلحات أساسية
    # earthquake / flood / drought / wildfire / forest fire notification
    t = re.sub(r"\bearthquake\b", "زلزال", t, flags=re.I)
    t = re.sub(r"\bflood alert\b", "تنبيه فيضانات", t, flags=re.I)
    t = re.sub(r"\bdrought\b", "جفاف", t, flags=re.I)
    t = re.sub(r"\bforest fire notification\b", "تنبيه حرائق غابات", t, flags=re.I)
    t = re.sub(r"\bwildfire\b", "حرائق غابات", t, flags=re.I)

    # Magnitude / Depth
    t = re.sub(r"\bMagnitude\b", "قوة", t, flags=re.I)
    t = re.sub(r"\bDepth\b", "عمق", t, flags=re.I)

    # in <Country>
    t = re.sub(r"\bin\s+", "في ", t, flags=re.I)

    # Few people affected / No people affected / unknown
    t = re.sub(r"\bFew people affected\b", "تأثر محدود", t, flags=re.I)
    t = re.sub(r"\bNo people affected\b", "لا يوجد تأثير على السكان", t, flags=re.I)
    t = re.sub(r"\[unknown\]", "غير معروف", t, flags=re.I)

    # تنظيف HTML entities إن ظهرت
    t = t.replace("&gt;", ">").replace("&amp;", "&")

    # تنسيق عربي بسيط للفواصل
    t = t.replace(",", "،")

    # لو ما كان عنده prefix (لون) نخليه بدون
    if prefix:
        # إذا السطر أصلاً يبدأ بأيقونة 🌍 نحتفظ بها ونضيف بعدها
        if t.startswith("🌍"):
            return f"🌍 {prefix} {t[1:].strip()}"
        return f"🌍 {prefix} {t}"
    else:
        # إذا ما جانا لون، نخلي 🌍 فقط
        if t.startswith("🌍"):
            return t
        return f"🌍 {t}"


def _lines_from_titles(items, limit=12, section=None):
    out = []
    for e in (items or [])[:limit]:
        t = (e.get("title") or "").strip()
        if not t:
            continue
        if section == "gdacs":
            t = _arabize_gdacs_title(t)
        out.append(f"- {t}")
    return out if out else ["- لا يوجد"]


def _pick_top_event(grouped):
    priority = ["fires", "gdacs", "ukmto", "ais", "food", "dust", "other"]
    for k in priority:
        if grouped.get(k):
            t = (grouped[k][0].get("title") or "").strip()
            if t:
                if k == "gdacs":
                    return _arabize_gdacs_title(t)
                return t
    return "لا يوجد"


def _build_report_text(report_title, grouped, include_ais=True):
    now = _now_ksa().strftime("%Y-%m-%d %H:%M KSA")
    top_event = _pick_top_event(grouped)

    # مؤشر مبسّط (حسب وجود أقسام)
    risk_score = 0
    if grouped.get("fires"):
        risk_score = max(risk_score, 55)
    if grouped.get("gdacs"):
        risk_score = max(risk_score, 30)
    if grouped.get("ukmto"):
        risk_score = max(risk_score, 35)
    if include_ais and grouped.get("ais"):
        risk_score = max(risk_score, 25)

    if risk_score >= 70:
        risk_level = "🟠 مرتفع"
    elif risk_score >= 40:
        risk_level = "🟡 مراقبة"
    else:
        risk_level = "🟢 منخفض"

    text = []
    text.append(f"{report_title}")
    text.append(f"🕒 تاريخ ووقت التحديث: {now}")
    text.append("")
    text.append("════════════════════")
    text.append("1️⃣ الملخص التنفيذي")
    text.append("")
    text.append(f"📊 مؤشر المخاطر الموحد: {risk_score}/100")
    text.append(f"📌 مستوى المخاطر: {risk_level}")
    text.append("")
    text.append("📍 أبرز حدث خلال آخر 6 ساعات:")
    text.append(f"{top_event}")
    text.append("")
    text.append("🧾 تفسير تشغيلي:")
    if grouped.get("fires"):
        text.append("• العامل الرئيسي: مؤشرات حرائق/نقاط رصد نشطة داخل المملكة (للاطلاع).")
    else:
        text.append("• العامل الرئيسي: لا توجد مؤشرات حرائق داخل المملكة حالياً.")
    if grouped.get("gdacs"):
        text.append("• GDACS: حدث/أحداث ضمن النطاق (للتوعية).")
    text.append("")
    text.append("════════════════════")
    text.append("2️⃣ مؤشرات سلاسل الإمداد الغذائي")
    text.extend(_lines_from_titles(grouped.get("food"), section="food"))
    text.append("")
    text.append("════════════════════")
    text.append("3️⃣ الكوارث الطبيعية")
    # نخليها 10 مثل ما عندك، تقدر تخفضها لـ5 لو تبي
    text.extend(_lines_from_titles(grouped.get("gdacs"), limit=10, section="gdacs"))
    text.append("")
    text.append("════════════════════")
    text.append("4️⃣ حرائق الغابات")
    text.extend(_lines_from_titles(grouped.get("fires"), limit=30, section="fires"))
    text.append("")
    text.append("════════════════════")
    text.append("5️⃣ الأحداث والتحذيرات البحرية")
    text.extend(_lines_from_titles(grouped.get("ukmto"), section="ukmto"))
    text.append("")
    text.append("════════════════════")
    text.append("6️⃣ حركة السفن وازدحام الموانئ")
    if include_ais:
        text.extend(_lines_from_titles(grouped.get("ais"), section="ais"))
    else:
        text.append("- لا يوجد")
    text.append("")
    text.append("════════════════════")
    text.append("7️⃣ ملاحظات تشغيلية")
    text.append("• تم إعداد التقرير آليًا بناءً على مصادر الرصد المعتمدة.")
    text.append("• يتم إصدار تنبيه إضافي عند ظهور أحداث جديدة مؤثرة.")

    return "\n".join(text)


def run(
    report_title="📄 تقرير الرصد والتحديث التشغيلي",
    report_id=None,
    only_if_new=False,
    include_ais=True,
    events=None,
):
    """
    متوافق مع main.py عندك:
    report_official.run(report_title=..., report_id=..., only_if_new=..., include_ais=..., events=...)
    """
    if events is None:
        events = []

    grouped = _group_events(events)
    report_text = _build_report_text(report_title, grouped, include_ais=include_ais)

    print(report_text)

    # منع الإرسال إذا ما فيه تغيير (اختياري)
    if only_if_new and report_id:
        state = _load_state()
        new_hash = _sha(report_text)
        old_hash = state.get(report_id)
        if old_hash == new_hash:
            print("ℹ️ لا يوجد تغيير في التقرير (only_if_new=True) — تم تجاوز الإرسال.")
            return report_text
        state[report_id] = new_hash
        _save_state(state)

    # إرسال تيليجرام بدون ما يكسر التشغيل
    try:
        _tg_send(report_text)
    except Exception as e:
        print(f"⚠️ فشل إرسال Telegram (لن نوقف التشغيل): {e}")

    return report_text
