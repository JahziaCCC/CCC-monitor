import os
import json
import hashlib
from datetime import datetime, timezone

import requests

import report_official

# الموديولات (إذا عندك بعضها باسم مختلف، غيّر الاسم هنا فقط)
import mon_dust
# اختياري: إذا عندك هذه الملفات بالفعل
try:
    import mon_gdacs
except Exception:
    mon_gdacs = None

try:
    import mon_ukmto
except Exception:
    mon_ukmto = None

try:
    import mon_ais_ports
except Exception:
    mon_ais_ports = None

# ✅ الزلازل
import mon_quakes


BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

STATE_FILE = "mewa_state.json"


def _load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _send_telegram(text: str):
    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "disable_web_page_preview": True
    }
    r = requests.post(url, json=payload, timeout=25)
    r.raise_for_status()


def _next_report_no(state):
    # مثال: RPT-20260222-013
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    n = int(state.get("report_seq", 0)) + 1
    state["report_seq"] = n
    return f"RPT-{today}-{n:03d}"


def _dedupe_key(text: str):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def main():
    state = _load_state()
    events = []

    # 1) الغبار
    try:
        events += mon_dust.fetch()
    except Exception:
        pass

    # 2) GDACS (اختياري)
    if mon_gdacs:
        try:
            events += mon_gdacs.fetch()
        except Exception:
            pass

    # 3) UKMTO (اختياري)
    if mon_ukmto:
        try:
            events += mon_ukmto.fetch()
        except Exception:
            pass

    # 4) AIS Ports (اختياري)
    if mon_ais_ports:
        try:
            events += mon_ais_ports.fetch()
        except Exception:
            pass

    # ✅ 5) زلازل USGS داخل السعودية (≥ 3.0)
    try:
        events += mon_quakes.fetch()
    except Exception:
        pass

    report_no = _next_report_no(state)
    report_text = report_official.build_official_report(events, state, report_no)

    # منع التكرار إذا نفس النص (اختياري لكنه مفيد)
    key = _dedupe_key(report_text)
    if state.get("last_report_key") == key:
        # لا نرسل نفس التقرير
        _save_state(state)
        return

    state["last_report_key"] = key
    _save_state(state)

    _send_telegram(report_text)


if __name__ == "__main__":
    main()
