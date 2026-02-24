# report_official.py (PRO+ MODE: Dust + Fires Smart Alerts)
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

# ===== PRO Settings =====
REPORT_MODE = os.environ.get("REPORT_MODE", "ALERT_ONLY").strip().upper()
DAILY_SUMMARY_HOURS = os.environ.get("DAILY_SUMMARY_HOURS", "6,18").strip()
REPORT_MIN_RISK_TO_SEND = int(os.environ.get("REPORT_MIN_RISK_TO_SEND", "35"))
SEND_ON_LEVEL_CHANGE = os.environ.get("SEND_ON_LEVEL_CHANGE", "1").strip() == "1"
SEND_ON_HIGHLIGHT_CHANGE = os.environ.get("SEND_ON_HIGHLIGHT_CHANGE", "1").strip() == "1"

# ===== Smart Alert: Dust =====
ALERT_PM10 = int(os.environ.get("ALERT_PM10", "2000"))
ALERT_PM10_CLEAR = int(os.environ.get("ALERT_PM10_CLEAR", "1500"))
ALERT_COOLDOWN_MIN = int(os.environ.get("ALERT_COOLDOWN_MIN", "120"))

# ===== Smart Alert: Fires (NEW) =====
ALERT_FIRES_COUNT = int(os.environ.get("ALERT_FIRES_COUNT", "200"))
ALERT_FIRES_FRP = float(os.environ.get("ALERT_FIRES_FRP", "80"))
ALERT_FIRES_CLEAR_COUNT = int(os.environ.get("ALERT_FIRES_CLEAR_COUNT", "100"))
ALERT_FIRES_CLEAR_FRP = float(os.environ.get("ALERT_FIRES_CLEAR_FRP", "60"))
ALERT_FIRES_COOLDOWN_MIN = int(os.environ.get("ALERT_FIRES_COOLDOWN_MIN", "180"))

# ===== Dust spread scoring (PRO) =====
DUST_SPREAD_WARN = int(os.environ.get("DUST_SPREAD_WARN", "1"))
DUST_SPREAD_HIGH = int(os.environ.get("DUST_SPREAD_HIGH", "3"))
DUST_SPREAD_CRIT = int(os.environ.get("DUST_SPREAD_CRIT", "5"))
# ===============================

def _now_ksa():
    return datetime.datetime.now(tz=KSA_TZ)

def _now_utc():
    return datetime.datetime.now(tz=datetime.timezone.utc)

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

def _parse_hours_csv(s: str):
    out = set()
    for part in (s or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            h = int(part)
            if 0 <= h <= 23:
                out.add(h)
        except Exception:
            pass
    return out

def _is_daily_summary_time(now_ksa: datetime.datetime):
    hours = _parse_hours_csv(DAILY_SUMMARY_HOURS)
    return (now_ksa.hour in hours) and (0 <= now_ksa.minute <= 5)

def _group_events(events):
    grouped = {
        "dust": [],
        "food": [],
        "gdacs": [],
        "fires": [],
        "ukmto": [],
        "ais": [],
        "pm10_list": [],
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

# يدعم 3,255 و 3٬255 و 3 255 و 3255
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
    best = None  # (value, title)
    for e in dust_items:
        t = e.get("title", "")
        v = _parse_best_int(t)
        if v is not None:
            if best is None or v > best[0]:
                best = (v, t)
    return best

def _dust_spread_score(dust_count: int):
    if dust_count >= DUST_SPREAD_CRIT:
        return 25
    if dust_count >= DUST_SPREAD_HIGH:
        return 15
    if dust_count >= DUST_SPREAD_WARN:
        return 7
    return 0

def _risk_score(grouped):
    score = 0

    top = _extract_top_dust(grouped["dust"])
    if top:
        v = top[0]
        if v >= 2500:
            score += 40
        elif v >= 1500:
            score += 28
        elif v >= 600:
            score += 18
        elif v >= 300:
            score += 10

    dust_count = len([e for e in grouped["dust"] if (e.get("title") or "").strip()])
    score += _dust_spread_score(dust_count)

    for e in grouped["gdacs"]:
        t = (e.get("title") or "").lower()
        if "red" in t:
            score += 35
        elif "orange" in t:
            score += 20
        elif "yellow" in t:
            score += 10

    # Fires scoring
    if grouped["fires"]:
        c = 0
        max_frp = 0.0
        for e in grouped["fires"]:
            try:
                c = max(c, int(e.get("count") or 0))
            except Exception:
                pass
            try:
                max_frp = max(max_frp, float(e.get("max_frp") or 0))
            except Exception:
                pass

        if c >= 200:
            score += 28
        elif c >= 100:
            score += 20
        elif c >= 20:
            score += 12
        elif c >= 1:
            score += 6

        if max_frp >= 80:
            score += 10
        elif max_frp >= 50:
            score += 6

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
    for e in grouped["gdacs"]:
        t = e.get("title") or ""
        if ("Saudi" in t) or ("السعودية" in t) or ("KSA" in t):
            return t

    top = _extract_top_dust(grouped["dust"])
    if top:
        return top[1]

    if grouped["fires"]:
        # إذا ما فيه غبار، أبرز الحرائق
        return grouped["fires"][0].get("title") or "لا يوجد"

    if grouped["gdacs"]:
        return grouped["gdacs"][0].get("title") or "لا يوجد"

    for k in ["ukmto", "ais"]:
        if grouped[k]:
            return grouped[k][0].get("title") or "لا يوجد"

    return "لا يوجد"

# ===================== SMART ALERTS =====================

def _minutes_since(ts_iso: str):
    if not ts_iso:
        return None
    try:
        dt = datetime.datetime.fromisoformat(ts_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        delta = _now_utc() - dt.astimezone(datetime.timezone.utc)
        return int(delta.total_seconds() // 60)
    except Exception:
        return None

def _smart_alert_dust(grouped, state):
    top = _extract_top_dust(grouped["dust"])
    max_val = top[0] if top else None
    max_title = top[1] if top else None

    prev_status = state.get("dust_alert_status", "normal")  # normal | severe
    last_sent_iso = state.get("dust_alert_last_sent_iso", "")
    mins = _minutes_since(last_sent_iso)

    def cooldown_ok():
        return (mins is None) or (mins >= ALERT_COOLDOWN_MIN)

    now_ksa = _now_ksa()
    stamp = now_ksa.strftime("%Y-%m-%d %H:%M")

    if max_val is not None and max_val >= ALERT_PM10:
        if prev_status != "severe" or cooldown_ok():
            msg = (
                "🚨 تنبيه فوري — غبار شديد جداً (PM10)\n"
                f"🕒 {stamp} (توقيت السعودية)\n\n"
                f"📍 الأعلى حالياً:\n{max_title}\n\n"
                f"📌 معيار التنبيه: PM10 ≥ {ALERT_PM10} µg/m³\n"
                "✅ المصدر: الرصد الآلي"
            )
            _tg_send(msg)
            state["dust_alert_status"] = "severe"
            state["dust_alert_last_sent_iso"] = _now_utc().isoformat()
            state["dust_alert_last_value"] = int(max_val)
            state["dust_alert_last_title"] = max_title
            _save_state(state)

    if prev_status == "severe":
        if (max_val is None) or (max_val < ALERT_PM10_CLEAR):
            mins2 = _minutes_since(state.get("dust_alert_last_sent_iso", ""))
            if (mins2 is None) or (mins2 >= ALERT_COOLDOWN_MIN):
                last_title = state.get("dust_alert_last_title", "")
                last_value = state.get("dust_alert_last_value", "")
                msg = (
                    "✅ إشعار — تحسن حالة الغبار الشديد (PM10)\n"
                    f"🕒 {stamp} (توقيت السعودية)\n\n"
                    f"📍 آخر حالة كانت:\n{last_title}\n"
                    f"📉 القيمة السابقة: {last_value} µg/m³\n\n"
                    f"📌 معيار الإنهاء: PM10 < {ALERT_PM10_CLEAR} µg/m³\n"
                    "✅ المصدر: الرصد الآلي"
                )
                _tg_send(msg)
                state["dust_alert_status"] = "normal"
                state["dust_alert_last_sent_iso"] = _now_utc().isoformat()
                _save_state(state)

def _extract_fires_metrics(fires_items):
    """
    يعتمد على mon_fires.py: event يحتوي count و max_frp إن توفر
    """
    count = 0
    max_frp = 0.0
    title = None
    latest = None
    for e in fires_items:
        t = (e.get("title") or "").strip()
        if t and t != "لا يوجد" and title is None:
            title = t
        try:
            count = max(count, int(e.get("count") or 0))
        except Exception:
            pass
        try:
            max_frp = max(max_frp, float(e.get("max_frp") or 0.0))
        except Exception:
            pass
        latest = e.get("latest_utc") or latest
    return count, max_frp, title, latest

def _smart_alert_fires(grouped, state):
    fires_count, fires_frp, fires_title, fires_latest = _extract_fires_metrics(grouped["fires"])

    prev_status = state.get("fires_alert_status", "normal")  # normal | active
    last_sent_iso = state.get("fires_alert_last_sent_iso", "")
    mins = _minutes_since(last_sent_iso)

    def cooldown_ok():
        return (mins is None) or (mins >= ALERT_FIRES_COOLDOWN_MIN)

    now_ksa = _now_ksa()
    stamp = now_ksa.strftime("%Y-%m-%d %H:%M")

    # ENTER: count>=threshold OR frp>=threshold
    trigger = (fires_count >= ALERT_FIRES_COUNT) or (fires_frp >= ALERT_FIRES_FRP)

    if trigger:
        if prev_status != "active" or cooldown_ok():
            msg = (
                "🚨 تنبيه فوري — حرائق نشطة (FIRMS)\n"
                f"🕒 {stamp} (توقيت السعودية)\n\n"
                f"📌 المؤشرات:\n"
                f"• عدد الرصد/24س: {fires_count}\n"
                f"• أعلى FRP: {fires_frp:.1f}\n"
            )
            if fires_latest:
                msg += f"• آخر تحديث FIRMS: {fires_latest}\n"
            if fires_title:
                msg += f"\n📍 ملخص:\n{fires_title}\n"
            msg += (
                f"\n📌 معيار التنبيه: Count≥{ALERT_FIRES_COUNT} أو FRP≥{ALERT_FIRES_FRP}\n"
                "✅ المصدر: الرصد الآلي"
            )
            _tg_send(msg)

            state["fires_alert_status"] = "active"
            state["fires_alert_last_sent_iso"] = _now_utc().isoformat()
            state["fires_alert_last_count"] = int(fires_count)
            state["fires_alert_last_frp"] = float(fires_frp)
            state["fires_alert_last_title"] = fires_title or ""
            _save_state(state)
            return

    # CLEAR: only if previously active, and now below clear thresholds
    if prev_status == "active":
        clear_ok = (fires_count < ALERT_FIRES_CLEAR_COUNT) and (fires_frp < ALERT_FIRES_CLEAR_FRP)
        if clear_ok and cooldown_ok():
            last_c = state.get("fires_alert_last_count", "")
            last_f = state.get("fires_alert_last_frp", "")
            msg = (
                "✅ إشعار — تحسن مؤشرات الحرائق (FIRMS)\n"
                f"🕒 {stamp} (توقيت السعودية)\n\n"
                f"📉 الحالة السابقة:\n"
                f"• Count: {last_c}\n"
                f"• FRP: {last_f}\n\n"
                f"📌 معيار الإنهاء: Count<{ALERT_FIRES_CLEAR_COUNT} و FRP<{ALERT_FIRES_CLEAR_FRP}\n"
                "✅ المصدر: الرصد الآلي"
            )
            _tg_send(msg)
            state["fires_alert_status"] = "normal"
            state["fires_alert_last_sent_iso"] = _now_utc().isoformat()
            _save_state(state)

def run_smart_alerts(events: list):
    grouped = _group_events(events)
    state = _load_state()
    _smart_alert_dust(grouped, state)
    _smart_alert_fires(grouped, state)

# ===================== REPORT =====================

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

def _should_send_report(text: str, score: int, level: str, highlight: str):
    if REPORT_MODE == "ALWAYS":
        return True

    now = _now_ksa()
    if _is_daily_summary_time(now):
        return True

    if score >= REPORT_MIN_RISK_TO_SEND:
        return True

    st = _load_state()
    prev_level = st.get("prev_level", "")
    prev_highlight = st.get("prev_highlight", "")

    if SEND_ON_LEVEL_CHANGE and prev_level and (prev_level != level):
        return True

    if SEND_ON_HIGHLIGHT_CHANGE and prev_highlight and (prev_highlight != highlight):
        return True

    return False

def run(title: str, events: list, only_if_new: bool = False):
    # 1) Smart Alerts (Dust + Fires) — فوري
    run_smart_alerts(events)

    # 2) Report build
    text = build_report_text(title=title, events=events)
    grouped = _group_events(events)
    score = _risk_score(grouped)
    level = _risk_level(score)
    highlight = _pick_highlight(grouped)

    # 3) PRO decision
    if not _should_send_report(text=text, score=score, level=level, highlight=highlight):
        st = _load_state()
        st["prev_level"] = level
        st["prev_highlight"] = highlight
        st["last_hash"] = _sha(text)
        _save_state(st)
        return

    # 4) Optional only_if_new
    if only_if_new:
        st = _load_state()
        h = _sha(text)
        if st.get("last_hash") == h:
            return
        st["last_hash"] = h
        st["prev_level"] = level
        st["prev_highlight"] = highlight
        _save_state(st)
    else:
        st = _load_state()
        st["prev_level"] = level
        st["prev_highlight"] = highlight
        st["last_hash"] = _sha(text)
        _save_state(st)

    _tg_send(text)
