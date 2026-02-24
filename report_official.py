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

# -----------------------
# Helpers
# -----------------------
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

    # retry بسيط لتفادي timeouts
    last_err = None
    for _ in range(3):
        try:
            r = requests.post(
                url,
                json={
                    "chat_id": CHAT_ID,
                    "text": text,
                    "disable_web_page_preview": True
                },
                timeout=30
            )
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

def _risk_level(score: int):
    # درجات بسيطة
    if score >= 80:
        return "🔴 حرج"
    if score >= 60:
        return "🟠 مرتفع"
    if score >= 35:
        return "🟡 مراقبة"
    return "🟢 منخفض"

def _score_from_grouped(grouped):
    # منطق بسيط: fires أعلى تأثير، ثم gdacs، ثم ukmto/ais/food
    fires_n = len(grouped.get("fires") or [])
    gdacs_n = len(grouped.get("gdacs") or [])
    ukmto_n = len(grouped.get("ukmto") or [])
    ais_n = len(grouped.get("ais") or [])
    food_n = len(grouped.get("food") or [])

    score = 0
    score += min(50, fires_n * 2)     # كل رصد حريق +2 (محدود 50)
    score += min(20, gdacs_n * 5)     # كل حدث GDACS +5 (محدود 20)
    score += min(10, ukmto_n * 5)     # UKMTO
    score += min(10, ais_n * 2)       # AIS
    score += min(10, food_n * 3)      # Food

    return int(min(100, score))

def _pick_top_event(grouped):
    # الأولوية: fires ثم ukmto ثم gdacs ثم food ثم ais
    for key in ["fires", "ukmto", "gdacs", "food", "ais", "other"]:
        items = grouped.get(key) or []
        if items:
            return (items[0].get("title") or "").strip() or "لا يوجد"
    return "لا يوجد"

def _build_report_text(report_title: str, grouped: dict, include_ais: bool = True):
    now_utc = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
    stamp = now_utc.strftime("%Y%m%d-%H%M%S")
    ts = now_utc.strftime("%Y-%m-%d %H:%M UTC")

    score = _score_from_grouped(grouped)
    level = _risk_level(score)
    top_event = _pick_top_event(grouped)

    # تقرير
    text = []
    text.append(f"{report_title}")
    text.append(f"رقم التقرير: RPT-{stamp}")
    text.append("الجهة المصدرة: نظام الرصد الآلي – مركز المتابعة")
    text.append("تصنيف التقرير: تشغيلي – للاستخدام الداخلي")
    text.append("")
    text.append("نطاق الرصد: المملكة والدول المجاورة")
    text.append(f"🕒 تاريخ ووقت التحديث: {ts}")
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
    text.append(f"{top_event if top_event else 'لا يوجد'}")
    text.append("")
    text.append("🧾 تفسير تشغيلي:")
    if grouped.get("fires"):
        text.append("• العامل الرئيسي: مؤشرات حرائق/نقاط رصد نشطة داخل المملكة (للاطلاع).")
    elif grouped.get("ukmto"):
        text.append("• العامل الرئيسي: تحذيرات/بلاغات بحرية (UKMTO).")
    elif grouped.get("gdacs"):
        text.append("• العامل الرئيسي: أحداث كوارث طبيعية إقليمية (GDACS).")
    else:
        text.append("• العامل الرئيسي: لا توجد مؤشرات داخل المملكة حالياً.")
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
    text.append("3️⃣ الكوارث الطبيعية (GDACS)")
    text.append("")
    # هنا نعرض نص عربي لو ما فيه أحداث
    gdacs_lines = _lines_from_titles(grouped.get("gdacs"), limit=8)
    if gdacs_lines == ["- لا يوجد"]:
        text.append("- لا يوجد أحداث ضمن النطاق حالياً.")
    else:
        text.extend(gdacs_lines)
    text.append("")
    text.append("════════════════════")
    text.append("4️⃣ حرائق الغابات (FIRMS)")
    text.append("")
    fires_lines = _lines_from_titles(grouped.get("fires"), limit=12)
    text.extend(fires_lines)
    text.append("")
    text.append("════════════════════")
    text.append("5️⃣ الأحداث والتحذيرات البحرية (UKMTO)")
    text.append("")
    text.extend(_lines_from_titles(grouped.get("ukmto"), limit=8))
    text.append("")
    text.append("════════════════════")
    text.append("6️⃣ حركة السفن وازدحام الموانئ (AIS)")
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

    return "\n".join([str(x) for x in text])  # ضمان نص فقط

# -----------------------
# Public entry used by main.py
# -----------------------
def run(events, report_title="📄 تقرير الرصد والتحديث التشغيلي", include_ais=True):
    grouped = _group_events(events or [])
    report_text = _build_report_text(report_title, grouped, include_ais=include_ais)

    # حفظ state بسيط لتتبع آخر تقرير
    state = _load_state()
    state["last_report_sha"] = _sha(report_text)
    state["last_report_at"] = _now_ksa().isoformat()
    _save_state(state)

    _tg_send(report_text)
    return report_text
