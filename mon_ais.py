import os, json, threading, datetime, requests, websocket

BOT = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
API_KEY = os.environ.get("AISSTREAM_API_KEY", "").strip()

if not BOT: raise RuntimeError("Missing TELEGRAM_BOT_TOKEN secret")
if not CHAT_ID: raise RuntimeError("Missing TELEGRAM_CHAT_ID secret")
if not API_KEY: raise RuntimeError("Missing AISSTREAM_API_KEY secret")

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
now = datetime.datetime.now(KSA_TZ)

CAPTURE_SECONDS = 180  # 3 دقائق

# =========================
# صناديق أصغر على ساحل السعودية (أفضل تغطية عادة)
# format: [[lat, lon],[lat, lon]]
# =========================
RED_SEA_BOXES = [
    [[16.2, 41.0], [18.5, 43.5]],  # جازان/الجنوب
    [[20.0, 38.0], [22.8, 40.8]],  # جدة/مكة الساحل
    [[23.0, 37.0], [25.5, 39.8]],  # ينبع/شمال جدة
    [[26.0, 35.0], [29.2, 38.6]],  # ضباء/نيوم تقريبًا
]

GULF_BOXES = [
    [[24.0, 48.0], [28.7, 51.8]],  # الدمام/الجبيل/رأس تنورة
    [[26.8, 50.8], [30.5, 55.5]],  # امتداد شمال شرق
]

ALL_BOXES = RED_SEA_BOXES + GULF_BOXES

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
    try: t = int(t)
    except: t = 0
    return 80 <= t <= 89

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    r = requests.post(url, json={"chat_id": CHAT_ID, "text": text}, timeout=25)
    print("TELEGRAM:", r.status_code, r.text)
    r.raise_for_status()

# =========================
# State during run
# =========================
samples_total = 0
samples_pos = 0
samples_static = 0

seen_red = set()
seen_gulf = set()

# ship types cache during the run
mmsi_to_type = {}

# instant oil sets (to avoid needing type+pos in same second)
oil_red = set()
oil_gulf = set()

# diagnostics: how many position reports hit each area
pos_hits_red = 0
pos_hits_gulf = 0

def extract_mmsi(data):
    meta = data.get("MetaData") or data.get("Metadata") or {}
    m = meta.get("MMSI") or meta.get("mmsi")
    if m: return str(m)
    mt = data.get("MessageType")
    try:
        if mt == "PositionReport":
            return str(data["Message"]["PositionReport"]["UserID"])
        if mt == "ShipStaticData":
            return str(data["Message"]["ShipStaticData"]["UserID"])
    except:
        return ""
    return ""

def on_open(ws):
    sub = {
        "APIKey": API_KEY,
        "BoundingBoxes": ALL_BOXES,
        "FilterMessageTypes": ["PositionReport", "ShipStaticData"]
    }
    ws.send(json.dumps(sub))
    print("Subscribed.")

def on_message(ws, message):
    global samples_total, samples_pos, samples_static, pos_hits_red, pos_hits_gulf
    samples_total += 1

    try:
        data = json.loads(message)
    except:
        return

    mt = data.get("MessageType")
    mmsi = extract_mmsi(data)
    if not mmsi:
        return

    if mt == "ShipStaticData":
        samples_static += 1
        try:
            s = data["Message"]["ShipStaticData"]
            vtype = int(s.get("Type", 0))
            if vtype:
                mmsi_to_type[mmsi] = vtype
                # لو السفينة كانت مرصودة مسبقًا داخل منطقة، حدّث قائمة ناقلات النفط فورًا
                if mmsi in seen_red and is_oil_tanker(vtype):
                    oil_red.add(mmsi)
                if mmsi in seen_gulf and is_oil_tanker(vtype):
                    oil_gulf.add(mmsi)
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
            return

        in_red = in_any(lat, lon, RED_SEA_BOXES)
        in_gulf = in_any(lat, lon, GULF_BOXES)

        if in_red:
            pos_hits_red += 1
            seen_red.add(mmsi)
            vtype = mmsi_to_type.get(mmsi, 0)
            if is_oil_tanker(vtype):
                oil_red.add(mmsi)

        if in_gulf:
            pos_hits_gulf += 1
            seen_gulf.add(mmsi)
            vtype = mmsi_to_type.get(mmsi, 0)
            if is_oil_tanker(vtype):
                oil_gulf.add(mmsi)

def on_error(ws, error):
    print("WS ERROR:", error)

def on_close(ws, code, reason):
    print("WS CLOSED:", code, reason)

def run_capture(seconds):
    ws = websocket.WebSocketApp(
        "wss://stream.aisstream.io/v0/stream",
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    timer = threading.Timer(seconds, lambda: ws.close())
    timer.start()
    ws.run_forever(ping_interval=20, ping_timeout=10)
    timer.cancel()

def build_report():
    return f"""🚢 تقرير الحركة البحرية – البحر الأحمر والخليج العربي
🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA

════════════════════
📡 نافذة الالتقاط: {samples_total} رسالة (≈ {CAPTURE_SECONDS} ثانية)
• PositionReport: {samples_pos}
• ShipStaticData: {samples_static}

📊 إجمالي السفن (فريدة داخل النطاق):
• البحر الأحمر: {len(seen_red)}
• الخليج العربي: {len(seen_gulf)}

🛢️ ناقلات النفط (Type 80–89):
• البحر الأحمر: {len(oil_red)}
• الخليج العربي: {len(oil_gulf)}

════════════════════
🔎 تشخيص سريع:
• Position hits (Red Sea): {pos_hits_red}
• Position hits (Gulf): {pos_hits_gulf}

📍 ملاحظات تشغيلية:
• إذا Red Sea hits = 0 فهذا يعني تغطية AISStream/النافذة ما التقطت إشارات داخل ساحل البحر الأحمر.
• ناقلات النفط تعتمد على توفر ShipStaticData لنفس MMSI (قد تتحسن مع تشغيلات لاحقة).
"""

if __name__ == "__main__":
    run_capture(CAPTURE_SECONDS)
    send_telegram(build_report())
    print("AIS report sent.")
