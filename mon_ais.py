import os
import datetime
import requests

# =========================
# Telegram
# =========================
BOT = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
now = datetime.datetime.now(KSA_TZ)

# =========================
# Dummy counts (replace later with AIS source)
# =========================
RED_SEA_SHIPS = 134
GULF_SHIPS = 98

PORTS_RED_SEA = ["ميناء جدة الإسلامي", "ميناء ينبع", "ميناء ضباء", "ميناء نيوم"]
PORTS_GULF = ["ميناء الملك عبدالعزيز (الدمام)", "ميناء الجبيل التجاري", "رأس تنورة (منطقة نفطية)"]

def send_telegram(text: str):
    if not BOT:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN secret")
    if not CHAT_ID:
        raise RuntimeError("Missing TELEGRAM_CHAT_ID secret")

    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    r = requests.post(url, json={"chat_id": CHAT_ID, "text": text}, timeout=25)

    # مهم جدًا للتشخيص في الـ Actions logs
    print("TELEGRAM STATUS:", r.status_code)
    print("TELEGRAM RESPONSE:", r.text)

    r.raise_for_status()

def build_report() -> str:
    ports_rs = "\n".join([f"• {p}" for p in PORTS_RED_SEA])
    ports_gf = "\n".join([f"• {p}" for p in PORTS_GULF])

    return f"""🚢 تقرير الحركة البحرية – البحر الأحمر والخليج العربي
🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA

════════════════════
📊 حركة السفن (تقديري/تشغيلي):
• البحر الأحمر: {RED_SEA_SHIPS} سفينة
• الخليج العربي: {GULF_SHIPS} سفينة

⚓ الموانئ ضمن النطاق:
🔴 البحر الأحمر:
{ports_rs}

🟦 الخليج العربي:
{ports_gf}

════════════════════
📍 ملاحظات تشغيلية:
• هذا تقرير تشغيل أولي (Baseline).
• سيتم إضافة مصدر AIS فعلي + ازدحام الموانئ + تنبيهات ذكية.
"""

if __name__ == "__main__":
    msg = build_report()
    send_telegram(msg)
    print("AIS report sent successfully.")
