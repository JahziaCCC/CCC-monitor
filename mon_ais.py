import os
import json
import time
import threading
import datetime
import requests
import websocket

# =========================
# Secrets
# =========================
BOT = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
API_KEY = os.environ.get("AISSTREAM_API_KEY", "").strip()

if not BOT:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN secret")
if not CHAT_ID:
    raise RuntimeError("Missing TELEGRAM_CHAT_ID secret")
if not API_KEY:
    raise RuntimeError("Missing AISSTREAM_API_KEY secret")

# =========================
# Time
# =========================
KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
now = datetime.datetime.now(KSA_TZ)

# =========================
# Bounding Boxes (2 boxes)
# format: [[[lat1, lon1], [lat2, lon2]], ...]
# per AISStream docs  [oai_citation:3‡aisstream.io](https://aisstream.io/documentation)
# =========================
BOX_RED_SEA = [[12.0, 32.0], [30.0, 44.0]]
BOX_GULF    = [[22.0, 47.0], [31.0, 57.0]]

# =========================
# Counters (unique by MMSI)
# =========================
seen_red = set()
seen_gulf = set()

# ship type map from ShipStaticData
mmsi_to_type = {}

def in_box(lat, lon, box):
    (lat1, lon1), (lat2, lon2) = box
    min_lat, max_lat = sorted([lat1, lat2])
    min_lon, max_lon = sorted([lon1, lon2])
    return (min_lat <= lat <= max_lat) and (min_lon <= lon <= max_lon)

def is_oil_tanker(ais_type: int) -> bool:
    # AIS type 80-89 are tankers (commonly used for oil/chemical variants)
    return 80 <= int(ais_type) <= 89

def send_telegram(text: str):
    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    r = requests.post(url, json={"chat_id": CHAT_ID, "text": text}, timeout=25)
    print("TELEGRAM STATUS:", r.status_code)
    print("TELEGRAM RESPONSE:", r.text)
    r.raise_for_status()

def build_report(red_total, gulf_total, red_oil, gulf_oil, samples):
    return f"""🚢 تقرير الحركة البحرية – البحر الأحمر والخليج العربي
🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA

════════════════════
📡 نافذة الالتقاط: {samples} رسالة (≈ 60 ثانية)

📊 إجمالي السفن (فريدة داخل الصندوق):
• البحر الأحمر: {red_total}
• الخليج العربي: {gulf_total}

🛢️ ناقلات النفط (حسب ShipStaticData.Type):
• البحر الأحمر: {red_oil}
• الخليج العربي: {gulf_oil}

════════════════════
📍 ملاحظة:
• AISStream قد يعطي تغطية أعلى قرب السواحل ومحطات الاستقبال.
"""

# =========================
# WebSocket handlers
# =========================
samples = 0

def on_message(ws, message):
    global samples
    samples += 1

    try:
        data = json.loads(message)
    except:
        return

    msg_type = data.get("MessageType")
    meta = data.get("MetaData", {}) or data.get("Metadata", {})  # احتياط

    # MMSI
    mmsi = meta.get("MMSI") or meta.get("mmsi")
    if not mmsi:
        # fallback: PositionReport.UserID
        try:
            mmsi = data["Message"]["PositionReport"]["UserID"]
        except:
            try:
                mmsi = data["Message"]["ShipStaticData"]["UserID"]
            except:
                mmsi = None
    if not mmsi:
        return
    mmsi = str(mmsi)

    # ShipStaticData: save vessel type
    if msg_type == "ShipStaticData":
        try:
            vessel_type = int(data["Message"]["ShipStaticData"].get("Type", 0))
            if vessel_type:
                mmsi_to_type[mmsi] = vessel_type
        except:
            pass
        return

    # PositionReport: count unique ships by box using PositionReport lat/lon  [oai_citation:4‡aisstream.io](https://aisstream.io/documentation)
    if msg_type == "PositionReport":
        try:
            pr = data["Message"]["PositionReport"]
            lat = float(pr["Latitude"])
            lon = float(pr["Longitude"])
        except:
            # fallback to MetaData if needed
            try:
                lat = float(meta.get("latitude"))
                lon = float(meta.get("longitude"))
            except:
                return

        if in_box(lat, lon, BOX_RED_SEA):
            seen_red.add(mmsi)
        if in_box(lat, lon, BOX_GULF):
            seen_gulf.add(mmsi)

def on_error(ws, error):
    print("WS ERROR:", error)

def on_close(ws, close_status_code, close_msg):
    print("WS CLOSED:", close_status_code, close_msg)

def on_open(ws):
    # Subscribe message format per docs  [oai_citation:5‡aisstream.io](https://aisstream.io/documentation)
    sub = {
        "APIKey": API_KEY,
        "BoundingBoxes": [BOX_RED_SEA, BOX_GULF],
        "FilterMessageTypes": ["PositionReport", "ShipStaticData"]
    }
    ws.send(json.dumps(sub))
    print("Subscribed to AISStream.")

def run_capture(seconds=60):
    ws = websocket.WebSocketApp(
        "wss://stream.aisstream.io/v0/stream",
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )

    # close after N seconds
    timer = threading.Timer(seconds, lambda: ws.close())
    timer.start()

    ws.run_forever(
        ping_interval=20,
        ping_timeout=10
    )

    timer.cancel()

if __name__ == "__main__":
    # collect for ~60 sec
    try:
        run_capture(60)
    except Exception as e:
        print("Capture exception:", e)

    # compute oil tankers among those seen
    red_oil = sum(1 for m in seen_red if is_oil_tanker(mmsi_to_type.get(m, 0)))
    gulf_oil = sum(1 for m in seen_gulf if is_oil_tanker(mmsi_to_type.get(m, 0)))

    report = build_report(
        red_total=len(seen_red),
        gulf_total=len(seen_gulf),
        red_oil=red_oil,
        gulf_oil=gulf_oil,
        samples=samples
    )
    send_telegram(report)
    print("AIS report sent.")
