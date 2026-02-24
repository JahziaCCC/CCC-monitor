# report_air.py (AIR/PM10 ONLY)
import os
import json
import hashlib
import datetime
import time
import requests

STATE_FILE = "state_air.json"
KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))

BOT = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

import mon_dusty  # <-- اسم ملفك الصحيح

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

def _tg_send(text: str, retries=3):
    if not BOT or not CHAT_ID:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    last_err = None

    for i in range(retries):
        try:
            r = requests.post(
                url,
                json={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True},
                timeout=40,
            )
            r.raise_for_status()
            return True
        except Exception as e:
            last_err = e
            time.sleep(2 + i * 2)

    print(f"[WARN] Telegram send failed after retries: {last_err}")
    return False

def build_air_report(dust_events):
    now_ksa = _now_ksa()
    now_utc = datetime.datetime.utcnow().replace(microsecond=0)
    report_id = f"AIR-{now_utc.strftime('%Y%m%d-%H%M%S')}"

    lines = []
    lines.append("📄 تقرير الغبار وجودة الهواء (PM10)")
    lines.append(f"رقم التقرير: {report_id}")
    lines.append("الجهة المصدرة: نظام الرصد الآلي – مركز المتابعة")
    lines.append("تصنيف التقرير: تشغيلي – للاستخدام الداخلي\n")
    lines.append("نطاق الرصد: المملكة العربية السعودية")
    lines.append(f"🕒 تاريخ ووقت التحديث: {now_utc.strftime('%Y-%m-%d %H:%M')} UTC")
    lines.append(f"🕒 (توقيت السعودية): {now_ksa.strftime('%Y-%m-%d %H:%M')}")
    lines.append("⏱️ آلية التحديث: تلقائي\n")

    lines.append("════════════════════")
    lines.append("1️⃣ مؤشرات الغبار وجودة الهواء (PM10)\n")

    if not dust_events:
        lines.append("- لا يوجد")
    else:
        for e in dust_events:
            t = (e.get("title") or "").strip()
            if t:
                lines.append(f"- {t}")

    lines.append("\n════════════════════")
    lines.append("2️⃣ ملاحظات تشغيلية\n")
    lines.append("• تم إعداد التقرير آليًا.")
    lines.append("• قد تظهر حالة (غير متاح مؤقتاً) بسبب حدود/تأخر مزود البيانات.")

    return "\n".join(lines)

def main():
    dust_events = []
    try:
        dust_events = mon_dusty.fetch()  # <-- لازم fetch() موجودة بملفك
    except Exception as e:
        print("[WARN] mon_dusty failed:", e)
        dust_events = []

    text = build_air_report(dust_events)

    state = _load_state()
    h = _sha(text)

    # يرسل فقط إذا تغير التقرير
    if state.get("last_hash") != h:
        _tg_send(text, retries=3)
        state["last_hash"] = h
        state["last_sent_at_utc"] = datetime.datetime.utcnow().isoformat()
        _save_state(state)
    else:
        print("[INFO] Air report unchanged; skipping Telegram.")

if __name__ == "__main__":
    main()
