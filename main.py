import os
import json
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

import requests

# استيراد مولد التقرير
from report_official import build_official_report

# =========================
# إعدادات عامة
# =========================

STATE_FILE = os.environ.get("STATE_FILE", "ccc_state.json")

# عتبات التنبيه (الخيار B)
ALERT_THRESHOLD = int(os.environ.get("ALERT_THRESHOLD", "70"))       # دخول الحرج
ALERT_RESET_BELOW = int(os.environ.get("ALERT_RESET_BELOW", "60"))   # إعادة التفعيل بعد الهدوء

# =========================
# Telegram
# =========================

def send_telegram(text: str) -> None:
    bot = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    url = f"https://api.telegram.org/bot{bot}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True
    }

    r = requests.post(url, json=payload, timeout=25)
    r.raise_for_status()


# =========================
# State
# =========================

def load_state() -> Dict[str, Any]:
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state: Dict[str, Any]) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# =========================
# Helpers
# =========================

def utc_now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def make_report_no(state: Dict[str, Any]) -> str:
    """
    مثال: RPT-20260223-002
    يزيد الرقم تلقائيًا يوميًا
    """
    today = datetime.now(timezone.utc).strftime("%Y%m%d")

    last_date = state.get("report_date")
    last_seq = int(state.get("report_seq", 0) or 0)

    if last_date != today:
        seq = 1
        state["report_date"] = today
        state["report_seq"] = seq
    else:
        seq = last_seq + 1
        state["report_seq"] = seq

    return f"RPT-{today}-{seq:03d}"


def extract_risk_score(report_text: str) -> int:
    """
    من سطر:
    📊 مؤشر المخاطر الموحد: 49/100
    """
    m = re.search(r"مؤشر المخاطر الموحد:\s*(\d+)\s*/\s*100", report_text)
    return int(m.group(1)) if m else -1


def extract_top_event(report_text: str) -> str:
    """
    بعد:
    📍 أبرز حدث خلال آخر 6 ساعات:
    """
    lines = [ln.strip() for ln in report_text.splitlines()]
    for i, ln in enumerate(lines):
        if "أبرز حدث خلال آخر 6 ساعات" in ln:
            for j in range(i + 1, min(i + 8, len(lines))):
                if lines[j]:
                    return lines[j]
    return "لا يوجد"


# =========================
# Early Warning (B)
# =========================

def should_send_critical_alert(state: Dict[str, Any], risk_score: int) -> bool:
    """
    B:
    - يرسل مرة واحدة عند دخول >= ALERT_THRESHOLD
    - لا يعيد الإرسال طالما alert_active=True
    - يسمح بالإرسال مرة أخرى فقط إذا نزل تحت ALERT_RESET_BELOW ثم ارتفع لاحقًا
    """
    alert_active = bool(state.get("alert_active", False))

    # إعادة التفعيل بعد الهدوء
    if alert_active and risk_score < ALERT_RESET_BELOW:
        state["alert_active"] = False
        state["alert_last_reset_at"] = utc_now_str()
        return False

    # أول دخول للحرج
    if (not alert_active) and risk_score >= ALERT_THRESHOLD:
        return True

    return False


def build_critical_alert_message(risk_score: int, top_event: str) -> str:
    return (
        "🚨 تنبيه تشغيلي عاجل\n\n"
        f"📊 مؤشر المخاطر: {risk_score}/100\n"
        "📌 المستوى: 🔴 حرج\n\n"
        "📍 السبب الرئيسي:\n"
        f"{top_event}\n\n"
        f"🕒 وقت التنبيه: {utc_now_str()}\n"
        "⚠️ يتطلب متابعة فورية."
    )


# =========================
# Collect events (Safe)
# =========================

def _safe_import(name: str):
    try:
        return __import__(name)
    except Exception:
        return None


def _safe_fetch(mod, fn_name: str = "fetch", *args, **kwargs) -> List[Dict[str, Any]]:
    """
    يشغّل fetch بأمان:
    - إذا ما فيه module أو ما فيه دالة fetch: يرجع []
    - إذا فيه خطأ: يرجع [] بدون ما يطيّح الـrun
    """
    if mod is None:
        return []
    fn = getattr(mod, fn_name, None)
    if not callable(fn):
        return []
    try:
        out = fn(*args, **kwargs)
        return out if isinstance(out, list) else []
    except Exception as e:
        # لا توقف الـrun — فقط سجّل السبب في الـlogs
        print(f"[WARN] {mod.__name__}.{fn_name} failed: {e}")
        return []


def collect_events(include_ais: bool = True) -> List[Dict[str, Any]]:
    """
    يتوقع وجود ملفات اختيارية:
    - mon_gdacs.py  => fetch()
    - mon_dust.py   => fetch()
    - mon_ukmto.py  => fetch()
    - mon_ais.py    => fetch()
    """
    events: List[Dict[str, Any]] = []

    mon_gdacs = _safe_import("mon_gdacs")
    mon_dust  = _safe_import("mon_dust")
    mon_ukmto = _safe_import("mon_ukmto")
    mon_ais   = _safe_import("mon_ais")

    events.extend(_safe_fetch(mon_gdacs, "fetch"))
    events.extend(_safe_fetch(mon_dust,  "fetch"))
    events.extend(_safe_fetch(mon_ukmto, "fetch"))

    if include_ais:
        events.extend(_safe_fetch(mon_ais, "fetch"))

    # تنظيف بسيط: نتأكد وجود keys الأساسية
    cleaned = []
    for e in events:
        if not isinstance(e, dict):
            continue
        e.setdefault("section", "other")
        e.setdefault("title", "")
        e.setdefault("meta", {})
        cleaned.append(e)

    return cleaned


# =========================
# Main
# =========================

def main():
    state = load_state()

    # اجمع الأحداث
    events = collect_events(include_ais=True)

    # رقم التقرير
    report_no = make_report_no(state)

    # ابنِ التقرير الرسمي (report_official.py)
    report_text = build_official_report(events, state, report_no)

    # استخراج قيم للتنبيه
    risk_score = extract_risk_score(report_text)
    top_event = extract_top_event(report_text)

    # 🚨 Early Warning (B)
    if risk_score >= 0 and should_send_critical_alert(state, risk_score):
        alert_msg = build_critical_alert_message(risk_score, top_event)
        send_telegram(alert_msg)

        state["alert_active"] = True
        state["alert_last_sent_at"] = utc_now_str()
        state["alert_last_score"] = risk_score
        state["alert_last_top_event"] = top_event

    # إرسال التقرير الرسمي
    send_telegram(report_text)

    # حفظ state
    save_state(state)


if __name__ == "__main__":
    main()
