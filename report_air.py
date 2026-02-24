# report_air.py
import os
import datetime
import requests
import json
import hashlib

import mon_dust

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
BOT = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

STATE_FILE = "air_state.json"

def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def _load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_state(state: dict):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def _tg_send(text: str):
    if not BOT or not CHAT_ID:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True}

    last_err = None
    for _ in range(3):
        try:
            r = requests.post(url, json=payload, timeout=45)
            r.raise_for_status()
            return
        except Exception as e:
            last_err = e
    raise last_err

def build_air_report(lines_pm10):
    now_utc = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
    rid = f"AIR-{now_utc.strftime('%Y%m%d-%H%M%S')}"

    lines = []
    lines.append("🌫️ تقرير الغبار وجودة الهواء (PM10) — تقرير منفصل")
    lines.append(f"رقم التقرير: {rid}")
    lines.append(f"🕒 التحديث: {now_utc.strftime('%Y-%m-%d %H:%M')} UTC")
    lines.append("")
    lines.append("════════════════════")
    lines.append("📍 قراءات المدن")
    lines.append("")
    lines.extend(lines_pm10 if lines_pm10 else ["- لا يوجد"])
    lines.append("")
    lines.append("════════════════════")
    lines.append("ملاحظات:")
    lines.append("• يتم توليد هذا التقرير تلقائيًا.")
    return rid, "\n".join(lines)

def main():
    only_if_new = os.environ.get("ONLY_IF_NEW_AIR", "1") == "1"

    events = mon_dust.fetch()  # يفترض يرجع titles جاهزة
    lines_pm10 = []
    for e in events:
        t = (e.get("title") or "").strip()
        if t:
            lines_pm10.append(t if t.startswith("-") else f"- {t}")

    rid, text = build_air_report(lines_pm10)

    state = _load_state()
    h = _sha(text)
    if only_if_new and state.get("last_hash") == h:
        return

    _tg_send(text)
    state["last_hash"] = h
    state["last_id"] = rid
    _save_state(state)

if __name__ == "__main__":
    main()
