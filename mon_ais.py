import os
import json
import threading
import datetime
import time
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

CAPTURE_SECONDS = 180
RETRY_ON_ZERO = 1
GLOBAL_TEST_SECONDS = 20

# =========================
# FINAL STABLE BOXES
# =========================

# البحر الأحمر (الساحل السعودي كامل)
RED_SEA_BOXES = [
    [[12.0, 32.0], [30.0, 44.5]]
]

# الخليج العربي
GULF_BOXES = [
    [[22.0, 47.0], [31.5, 57.0]]
]

ALL_BOXES = RED_SEA_BOXES + GULF_BOXES
GLOBAL_BOX = [[-90.0, -180.0], [90.0, 180.0]]

# =========================
# Helpers
# =========================
def normalize_box(box):
    (lat1, lon1), (lat2, lon2) = box
    min_lat, max_lat = sorted([lat1, lat2])
    min_lon, max_lon = sorted([lon1, lon2])
    return min_lat, max_lat, min_lon, max_lon

def in_box(lat, lon, box):
    min_lat, max_lat, min_lon, max_lon = normalize_box(box)
    return (min_lat <= lat <= max_lat) and (min_lon <= lon <= max_lon)

def in_any(lat, lon, boxes):
    return any(in_box(lat, lon, b) for b in boxes)

def is_oil_tanker(t):
    try:
        t = int(t)
    except:
        t = 0
    return 80 <= t <= 89

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    r = requests.post(url, json={"chat_id": CHAT_ID, "text": text}, timeout=25)
    print("TELEGRAM:", r.status_code)
    print(r.text)
    r.raise_for_status()

def extract_mmsi(data):
    meta = data.get("MetaData") or data.get("Metadata") or {}
    m = meta.get("MMSI") or meta.get("mmsi")
    if m:
        return str(m)

    msg = data.get("Message", {})
    for k in msg.keys():
        blk = msg.get(k, {})
        if isinstance(blk, dict) and "UserID" in blk:
            return str(blk["UserID"])
    return ""

def extract_lat_lon_any(data):
    msg = data.get("Message", {})
    for k, blk in msg.items():
        if isinstance(blk, dict) and ("Latitude" in blk) and ("Longitude" in blk):
            return float(blk["Latitude"]), float(blk["Longitude"]), blk

    meta = data.get("MetaData") or data.get("Metadata") or {}
    if "latitude" in meta and "longitude" in meta:
        return float(meta["latitude"]), float(meta["longitude"]), {}

    raise KeyError("No lat/lon")

# =========================
# Capture function
# =========================
def run_capture(boxes, seconds):

    samples_total = 0
    samples_pos = 0
    samples_static = 0

    seen_red = set()
    seen_gulf = set()

    oil_red = set()
    oil_gulf = set()

    mmsi_to_type = {}

    opened = False
    subsent = False
    last_error = ""

    pos_hits_red = 0
    pos_hits_gulf = 0

    def on_open(ws):
        nonlocal opened, subsent
        opened = True

        sub = {
            "APIKey": API_KEY,
            "BoundingBoxes": boxes
        }

        ws.send(json.dumps(sub))
        subsent = True
        print("Subscribed.")

    def on_message(ws, message):
        nonlocal samples_total, samples_pos, samples_static
        nonlocal pos_hits_red, pos_hits_gulf, last_error

        samples_total += 1

        if isinstance(message, str) and '"error"' in message:
            last_error = message
            return

        try:
            data = json.loads(message)
        except:
            return

        mmsi = extract_mmsi(data)
        if not mmsi:
            return

        mt = data.get("MessageType")

        if mt == "ShipStaticData":
            samples_static += 1
            try:
                vtype = int(data["Message"]["ShipStaticData"].get("Type", 0))
                if vtype:
                    mmsi_to_type[mmsi] = vtype
            except:
                pass
            return

        try:
            lat, lon, blk = extract_lat_lon_any(data)
        except:
            return

        samples_pos += 1

        vtype = 0
        if isinstance(blk, dict) and "Type" in blk:
            try:
                vtype = int(blk.get("Type", 0))
            except:
                pass

        if not vtype:
            vtype = mmsi_to_type.get(mmsi, 0)

        if in_any(lat, lon, RED_SEA_BOXES):
            pos_hits_red += 1
            seen_red.add(mmsi)
            if is_oil_tanker(vtype):
                oil_red.add(mmsi)

        if in_any(lat, lon, GULF_BOXES):
            pos_hits_gulf += 1
            seen_gulf.add(mmsi)
            if is_oil_tanker(vtype):
                oil_gulf.add(mmsi)

    ws = websocket.WebSocketApp(
        "wss://stream.aisstream.io/v0/stream",
        on_open=on_open,
        on_message=on_message
    )

    timer = threading.Timer(seconds, lambda: ws.close())
    timer.start()
    ws.run_forever(ping_interval=20, ping_timeout=10)
    timer.cancel()

    return {
        "samples_total": samples_total,
        "samples_pos": samples_pos,
        "samples_static": samples_static,
        "seen_red": seen_red,
        "seen_gulf": seen_gulf,
        "oil_red": oil_red,
        "oil_gulf": oil_gulf,
        "pos_hits_red": pos_hits_red,
        "pos_hits_gulf": pos_hits_gulf,
        "opened": opened,
        "subsent": subsent,
        "last_error": last_error
    }

# =========================
# MAIN
# =========================
if __name__ == "__main__":

    attempts = 0
    res = None

    for _ in range(RETRY_ON_ZERO + 1):
        attempts += 1
        res = run_capture(ALL_BOXES, CAPTURE_SECONDS)
        if res["samples_total"] > 0:
            break
        time.sleep(15)

    if res["samples_total"] == 0:

        global_res = run_capture([GLOBAL_BOX], GLOBAL_TEST_SECONDS)

        msg = f"""⚠️ AISStream تشخيص
🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA

• attempts: {attempts}
• opened: {res['opened']}
• subscription_sent: {res['subsent']}
• last_error: {res['last_error'] or "N/A"}

📌 اختبار عالمي:
• global_messages: {global_res['samples_total']}
• global_positions: {global_res['samples_pos']}
"""
        send_telegram(msg)

    else:

        msg = f"""🚢 تقرير الحركة البحرية – البحر الأحمر والخليج العربي
🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA

════════════════════
📡 نافذة الالتقاط: {res['samples_total']} رسالة (≈ {CAPTURE_SECONDS} ثانية)
• Position: {res['samples_pos']}
• ShipStaticData: {res['samples_static']}

📊 إجمالي السفن:
• البحر الأحمر: {len(res['seen_red'])}
• الخليج العربي: {len(res['seen_gulf'])}

🛢️ ناقلات النفط:
• البحر الأحمر: {len(res['oil_red'])}
• الخليج العربي: {len(res['oil_gulf'])}

════════════════════
🔎 Position hits:
• Red Sea: {res['pos_hits_red']}
• Gulf: {res['pos_hits_gulf']}
"""
        send_telegram(msg)

    print("DONE")
