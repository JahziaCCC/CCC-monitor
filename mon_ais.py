import os
import json
import threading
import datetime
import requests
import websocket

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
API_KEY = os.environ["AISSTREAM_API_KEY"]

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
now = datetime.datetime.now(KSA_TZ)

CAPTURE_SECONDS = 180

# =========================
# AREAS
# =========================
RED_SEA_BOXES = [
    [[12.0, 41.0], [29.8, 44.5]]
]

GULF_BOXES = [
    [[22.0, 47.0], [31.5, 57.0]]
]

ALL_BOXES = RED_SEA_BOXES + GULF_BOXES

def normalize_box(box):
    (lat1, lon1), (lat2, lon2) = box
    return min(lat1,lat2), max(lat1,lat2), min(lon1,lon2), max(lon1,lon2)

def in_box(lat, lon, box):
    a,b,c,d = normalize_box(box)
    return a <= lat <= b and c <= lon <= d

def in_any(lat, lon, boxes):
    return any(in_box(lat,lon,b) for b in boxes)

def send_telegram(text):
    requests.post(
        f"https://api.telegram.org/bot{BOT}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text},
        timeout=20
    )

def extract_mmsi(data):
    meta = data.get("MetaData") or {}
    return str(meta.get("MMSI",""))

def extract_latlon(data):
    msg = data.get("Message", {})
    for _, blk in msg.items():
        if isinstance(blk, dict):
            if "Latitude" in blk and "Longitude" in blk:
                return float(blk["Latitude"]), float(blk["Longitude"]), blk
    raise KeyError

def is_oil_tanker(vtype):
    try:
        v = int(vtype)
    except:
        v = 0
    return 80 <= v <= 89

# =========================
# MAIN CAPTURE
# =========================
def run_capture():

    seen_red = set()
    seen_gulf = set()

    oil_red = set()
    oil_gulf = set()

    samples_total = 0
    samples_pos = 0

    def on_open(ws):
        ws.send(json.dumps({
            "APIKey": API_KEY,
            "BoundingBoxes": ALL_BOXES
        }))

    def on_message(ws, message):
        nonlocal samples_total, samples_pos

        samples_total += 1

        try:
            data = json.loads(message)
            lat, lon, blk = extract_latlon(data)
            mmsi = extract_mmsi(data)
        except:
            return

        samples_pos += 1

        vtype = blk.get("Type",0)

        if in_any(lat, lon, RED_SEA_BOXES):
            seen_red.add(mmsi)
            if is_oil_tanker(vtype):
                oil_red.add(mmsi)

        if in_any(lat, lon, GULF_BOXES):
            seen_gulf.add(mmsi)
            if is_oil_tanker(vtype):
                oil_gulf.add(mmsi)

    ws = websocket.WebSocketApp(
        "wss://stream.aisstream.io/v0/stream",
        on_open=on_open,
        on_message=on_message
    )

    timer = threading.Timer(CAPTURE_SECONDS, lambda: ws.close())
    timer.start()
    ws.run_forever()
    timer.cancel()

    return samples_total, samples_pos, seen_red, seen_gulf, oil_red, oil_gulf

# =========================
# RISK INDEX
# =========================
def calculate_risk(gulf_count, red_count, oil_total):

    risk = 0

    # كثافة حركة الخليج
    if gulf_count > 50:
        risk += 40
    elif gulf_count > 20:
        risk += 25
    else:
        risk += 10

    # ناقلات النفط
    risk += min(oil_total * 5, 30)

    # غياب البحر الأحمر
    if red_count == 0:
        risk += 10

    # سقف
    risk = min(risk, 100)

    if risk >= 70:
        level = "🔴 مرتفع"
    elif risk >= 40:
        level = "🟠 متوسط"
    else:
        level = "🟢 منخفض"

    return risk, level

# =========================
# RUN
# =========================
if __name__ == "__main__":

    total, pos, red, gulf, oil_red, oil_gulf = run_capture()

    oil_total = len(oil_red) + len(oil_gulf)

    risk, level = calculate_risk(
        len(gulf),
        len(red),
        oil_total
    )

    red_text = str(len(red))
    if len(red) == 0:
        red_text = "⚠️ تغطية AIS ضعيفة"

    msg = f"""🚢 تقرير الحركة البحرية الذكي
🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA

════════════════════
📡 الرسائل: {total}
📍 Position: {pos}

📊 السفن:
• البحر الأحمر: {red_text}
• الخليج العربي: {len(gulf)}

🛢️ ناقلات النفط:
• الإجمالي: {oil_total}

════════════════════
📊 مؤشر المخاطر البحري:
{risk}/100 — {level}

📌 تفسير سريع:
• يعتمد على كثافة الحركة + ناقلات النفط + حالة التغطية.
"""

    send_telegram(msg)
