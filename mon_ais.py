import os, json, threading, datetime, requests, websocket

BOT = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
API_KEY = os.environ.get("AISSTREAM_API_KEY", "").strip()

if not BOT: raise RuntimeError("Missing TELEGRAM_BOT_TOKEN secret")
if not CHAT_ID: raise RuntimeError("Missing TELEGRAM_CHAT_ID secret")
if not API_KEY: raise RuntimeError("Missing AISSTREAM_API_KEY secret")

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
now = datetime.datetime.now(KSA_TZ)

CAPTURE_SECONDS = 180

# ✅ BoundingBoxes format per docs
# BoundingBoxes: [ [[lat,lon],[lat,lon]], [[lat,lon],[lat,lon]], ... ]   [oai_citation:2‡aisstream.io](https://aisstream.io/documentation)
BOX_RED_SEA = [[12.0, 32.0], [30.0, 44.0]]
BOX_GULF    = [[22.0, 47.0], [31.0, 57.0]]

def send_telegram(text: str):
    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    r = requests.post(url, json={"chat_id": CHAT_ID, "text": text}, timeout=25)
    r.raise_for_status()

def is_oil_tanker(t: int) -> bool:
    try: t = int(t)
    except: t = 0
    return 80 <= t <= 89

seen_red, seen_gulf = set(), set()
mmsi_to_type = {}

samples_total = 0
samples_pos = 0
samples_static = 0

opened = False
last_error_text = ""
close_code = None
close_reason = ""

def in_box(lat, lon, box):
    (lat1, lon1), (lat2, lon2) = box
    min_lat, max_lat = sorted([lat1, lat2])
    min_lon, max_lon = sorted([lon1, lon2])
    return (min_lat <= lat <= max_lat) and (min_lon <= lon <= max_lon)

def on_open(ws):
    global opened
    opened = True

    sub = {
        "APIKey": API_KEY,
        "BoundingBoxes": [BOX_RED_SEA, BOX_GULF],
        "FilterMessageTypes": ["PositionReport", "ShipStaticData"]
    }
    # ⚠️ subscription must be sent within 3 seconds or connection will close  [oai_citation:3‡aisstream.io](https://aisstream.io/documentation)
    ws.send(json.dumps(sub))
    print("Subscribed.")

def on_message(ws, message):
    global samples_total, samples_pos, samples_static, last_error_text
    samples_total += 1

    # التقط رسائل الخطأ لو رجعت
    if isinstance(message, str) and '"error"' in message:
        last_error_text = message
        print("SERVER ERROR:", message)
        return

    try:
        data = json.loads(message)
    except:
        return

    mt = data.get("MessageType")
    meta = data.get("MetaData") or data.get("Metadata") or {}

    # MMSI
    mmsi = meta.get("MMSI") or meta.get("mmsi")
    if not mmsi:
        try: mmsi = data["Message"]["PositionReport"]["UserID"]
        except:
            try: mmsi = data["Message"]["ShipStaticData"]["UserID"]
            except: mmsi = None
    if not mmsi:
        return
    mmsi = str(mmsi)

    if mt == "ShipStaticData":
        samples_static += 1
        try:
            vtype = int(data["Message"]["ShipStaticData"].get("Type", 0))
            if vtype:
                mmsi_to_type[mmsi] = vtype
        except:
            pass
        return

    if mt == "PositionReport":
        samples_pos += 1
        try:
            pr = data["Message"]["PositionReport"]
            lat = float(pr["Latitude"])
            lon = float(pr["Longitude"])
        except:
            # fallback from metadata lat/lon if present
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
    global last_error_text
    last_error_text = str(error)
    print("WS ERROR:", error)

def on_close(ws, code, reason):
    global close_code, close_reason
    close_code = code
    close_reason = reason or ""
    print("WS CLOSED:", code, reason)

def run_capture(seconds: int):
    ws = websocket.WebSocketApp(
        "wss://stream.aisstream.io/v0/stream",
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )

    timer = threading.Timer(seconds, lambda: ws.close())
    timer.start()
    ws.run_forever(ping_interval=20, ping_timeout=10)
    timer.cancel()

def build_report():
    red_total = len(seen_red)
    gulf_total = len(seen_gulf)
    red_oil = sum(1 for m in seen_red if is_oil_tanker(mmsi_to_type.get(m, 0)))
    gulf_oil = sum(1 for m in seen_gulf if is_oil_tanker(mmsi_to_type.get(m, 0)))

    return f"""🚢 تقرير الحركة البحرية – البحر الأحمر والخليج العربي
🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA

════════════════════
📡 نافذة الالتقاط: {samples_total} رسالة (≈ {CAPTURE_SECONDS} ثانية)
• PositionReport: {samples_pos}
• ShipStaticData: {samples_static}

📊 إجمالي السفن (فريدة داخل النطاق):
• البحر الأحمر: {red_total}
• الخليج العربي: {gulf_total}

🛢️ ناقلات النفط (Type 80–89):
• البحر الأحمر: {red_oil}
• الخليج العربي: {gulf_oil}
"""

def build_diag():
    return f"""⚠️ AISStream تشخيص اتصال
🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA

• opened: {opened}
• messages: {samples_total} (خلال {CAPTURE_SECONDS}s)
• close_code: {close_code}
• close_reason: {close_reason}
• last_error: {last_error_text or "N/A"}

✅ إجراءات سريعة:
1) تأكد AISSTREAM_API_KEY صحيح وغير موقوف.
2) شغل الـ workflow مرة ثانية.
3) إذا ظهر 'Api Key Is Not Valid' فالمفتاح غير صالح.  [oai_citation:4‡aisstream.io](https://aisstream.io/documentation)
"""

if __name__ == "__main__":
    try:
        run_capture(CAPTURE_SECONDS)
    except Exception as e:
        last_error_text = str(e)
        print("Capture exception:", e)

    if samples_total == 0:
        send_telegram(build_diag())
    else:
        send_telegram(build_report())

    print("Done.")
