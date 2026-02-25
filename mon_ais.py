import os
import json
import websocket
import datetime
import requests

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
API_KEY = os.environ["AISSTREAM_API_KEY"]

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
now = datetime.datetime.now(KSA_TZ)

# =========================
# مناطق الرصد (تقريبية)
# =========================
RED_SEA = {
    "minLat": 12,
    "maxLat": 30,
    "minLon": 32,
    "maxLon": 44,
}

GULF = {
    "minLat": 22,
    "maxLat": 31,
    "minLon": 47,
    "maxLon": 57,
}

# =========================
# Counters
# =========================
red_total = 0
gulf_total = 0
red_oil = 0
gulf_oil = 0

def in_box(lat, lon, box):
    return (
        box["minLat"] <= lat <= box["maxLat"]
        and box["minLon"] <= lon <= box["maxLon"]
    )

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    r = requests.post(url, json={"chat_id": CHAT_ID, "text": msg}, timeout=20)
    print(r.text)

def on_message(ws, message):
    global red_total, gulf_total, red_oil, gulf_oil

    data = json.loads(message)

    try:
        msg = data["Message"]["PositionReport"]
        lat = msg["Latitude"]
        lon = msg["Longitude"]
        ship_type = msg.get("ShipType", 0)

        # البحر الأحمر
        if in_box(lat, lon, RED_SEA):
            red_total += 1
            if 80 <= ship_type <= 89:
                red_oil += 1

        # الخليج العربي
        if in_box(lat, lon, GULF):
            gulf_total += 1
            if 80 <= ship_type <= 89:
                gulf_oil += 1

    except:
        pass

def build_report():
    return f"""🚢 تقرير الحركة البحرية – البحر الأحمر والخليج العربي
🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA

════════════════════
📊 إجمالي السفن:
• البحر الأحمر: {red_total}
• الخليج العربي: {gulf_total}

🛢️ ناقلات النفط:
• البحر الأحمر: {red_oil}
• الخليج العربي: {gulf_oil}

════════════════════
📍 ملاحظات تشغيلية:
• البيانات مباشرة من AISStream.
• تحديث كل ساعة.
"""

def run():
    ws = websocket.WebSocketApp(
        "wss://stream.aisstream.io/v0/stream",
        on_message=on_message,
    )

    sub_msg = {
        "APIKey": API_KEY,
        "BoundingBoxes": [[
            [12, 32],
            [30, 44]
        ],[
            [22, 47],
            [31, 57]
        ]]
    }

    def on_open(ws):
        ws.send(json.dumps(sub_msg))

    ws.on_open = on_open

    # تشغيل لمدة 60 ثانية فقط (عشان GitHub)
    ws.run_forever(dispatcher=None, reconnect=0)

if __name__ == "__main__":
    try:
        run()
    except:
        pass

    send_telegram(build_report())
    print("AIS report sent")
