import os
import datetime
import requests

BOT = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))

def send_telegram(text: str):
    if not BOT or not CHAT_ID:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    r = requests.post(url, json={"chat_id": CHAT_ID, "text": text})
    print("TELEGRAM status:", r.status_code)
    print("TELEGRAM response:", r.text)
    r.raise_for_status()

def build_report():
    now = datetime.datetime.now(KSA_TZ).strftime("%Y-%m-%d %H:%M")
    return f"""🌪️ تقرير الغبار (Dust Report)
🕒 تاريخ ووقت التحديث: {now} KSA

✅ الحالة: تم تشغيل نظام الغبار بنجاح
"""

if __name__ == "__main__":
    print("Running Dust Report...")
    msg = build_report()
    send_telegram(msg)
    print("Dust report sent successfully.")
