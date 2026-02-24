# report_air.py
import os
import json
import hashlib
import datetime
import requests

import mon_dust  # ✅ اسم ملفك الصحيح

STATE_FILE = "air_state.json"
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

    # Retry بسيط لأنك واجهت Telegram timeout
    last_err = None
    for _ in range(3):
        try:
            r = requests.post(url, json={
                "chat_id": CHAT_ID,
                "text": text,
                "disable_web_page_preview": True
            }, timeout=30)
            r.raise_for_status()
            return
        except Exception as e:
            last_err = e
    raise last_err

def build_air_text(events):
    ts_utc = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    header = []
    header.append("📄 تقرير جودة الهواء والغبار (PM10)")
    header.append(f"🕒 {ts_utc.strftime('%Y-%m-%d %H:%M UTC')}")
    header.append("⏱️ آلية التحديث: تلقائي")
    header.append("════════════════════")
    header.append("📍 مؤشرات الغبار وجودة الهواء (PM10)")
    header.append("")

    lines = []
    for e in events:
        if (e.get("section") or "").lower() == "dust":
            t = (e.get("title") or "").strip()
            if t:
                lines.append(f"- {t}")

    if not lines:
        lines = ["- لا يوجد"]

    # أضف أي ملاحظات تشغيلية (من section other)
    notes = []
    for e in events:
        if (e.get("section") or "").lower() == "other":
            t = (e.get("title") or "").strip()
            if t and "ملاحظة" in t:
                notes.append(f"• {t}")

    out = "\n".join(header + lines)
    if notes:
        out += "\n\n════════════════════\n📝 ملاحظات تشغيلية\n" + "\n".join(notes)

    return out

def main():
    state = _load_state()

    events = mon_dust.fetch(timeout=25)
    text = build_air_text(events)

    sig = _sha(text)
    if state.get("last_sig") == sig:
        # لا ترسل نفس الشي
        return

    _tg_send(text)
    state["last_sig"] = sig
    state["last_sent_ksa"] = _now_ksa().isoformat()
    _save_state(state)

if __name__ == "__main__":
    main()
