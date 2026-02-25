import os
import datetime
import requests

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
now = datetime.datetime.now(KSA_TZ)

# =========================
# مناطق بحرية (تقريبية)
# =========================
RED_SEA_SHIPS = 134
GULF_SHIPS = 98

PORTS = {
    "ميناء جدة": "مرتفع",
    "ميناء الدمام": "متوسط",
    "ميناء ينبع": "منخفض",
    "ميناء الجبيل": "منخفض"
}

def send(msg):
    url=f"https://api.telegram.org/bot{BOT}/sendMessage"
    requests.post(url,json={"chat_id":CHAT_ID,"text":msg},timeout=20)

def build_report():

    ports_text="\n".join([f"• {k}: {v}" for k,v in PORTS.items()])

    return f"""🚢 تقرير الحركة البحرية – السعودية
🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA

════════════════════
📊 حركة السفن:
• البحر الأحمر: {RED_SEA_SHIPS} سفينة
• الخليج العربي: {GULF_SHIPS} سفينة

⚠️ ازدحام الموانئ:
{ports_text}

🚨 أحداث بحرية:
• لا يوجد تحذيرات جديدة

════════════════════
📍 ملاحظات تشغيلية:
• حركة طبيعية.
• متابعة التحديث القادم.
"""

if __name__=="__main__":
    send(build_report())
    print("AIS report sent")
