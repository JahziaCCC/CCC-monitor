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

# =========================
# Capture / Retry
# =========================
CAPTURE_SECONDS = 180
RETRY_ON_ZERO = 2  # جرّب 3 محاولات إجماليًا (0..2)

# =========================
# Boxes (Coastal KSA focus)
# =========================
RED_SEA_BOXES = [
    [[16.2, 41.0], [18.5, 43.5]],  # جنوب (جازان تقريبًا)
    [[20.0, 38.0], [22.8, 40.8]],  # جدة/الساحل
    [[23.0, 37.0], [25.5, 39.8]],  # ينبع
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
    try:
        t = int(t)
    except:
        t = 0
    return 80 <= t <= 89

def send_telegram(text: str):
    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    r = requests.post(url, json={"chat_id": CHAT_ID, "text": text}, timeout=25)
    print("TELEGRAM:", r.status_code, r.text)
    r.raise_for_status()

def build_report(samples_total, samples_pos, samples_static,
                 seen_red, seen_gulf, oil_red, oil_gulf,
                 pos_hits_red, pos_hits_gulf):
    return f"""🚢 تقرير الحركة البحرية – البحر الأحمر والخليج العربي
🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA

════════════════════
📡 نافذة الالتقاط: {samples_total} رسالة (≈ {CAPTURE_SECONDS} ثانية)
• Position*: {samples_pos}
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
"""

def build_diag(opened, close_code, close_reason, last_error, attempts, subsent):
    return f"""⚠️ AISStream تشخيص اتصال
🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA

• attempts: {attempts}
• opened: {opened}
• subscription_sent: {subsent}
• close_code: {close_code}
• close_reason: {close_reason or "N/A"}
• last_error: {last_error or "N/A"}

📍 تفسير:
• opened=True + subscription_sent=True + messages=0
  = غالبًا Throttle/انقطاع مؤقت أو الدفق ما أعطى رسائل ضمن نافذة الالتقاط.
"""

def run_capture_once():
    # ===== state per attempt =====
    samples_total = 0
    samples_pos = 0
    samples_static = 0

    seen_red = set()
    seen_gulf = set()
    oil_red = set()
    oil_gulf = set()

    mmsi_to_type = {}

    pos_hits_red = 0
    pos_hits_gulf = 0

    opened = False
    subsent = False
    last_error = ""
    close_code = None
    close_reason = ""

    # ------- helpers -------
    def extract_mmsi(data):
        meta = data.get("MetaData") or data.get("Metadata") or {}
        m = meta.get("MMSI") or meta.get("mmsi")
        if m:
            return str(m)

        mt = data.get("MessageType")
        try:
            # fallback: most AISStream messages have UserID inside message blocks
            msg = data.get("Message", {})
            for k in ("PositionReport", "StandardClassBPositionReport", "ExtendedClassBPositionReport",
                      "BaseStationReport", "ShipStaticData"):
                if k in msg and "UserID" in msg[k]:
                    return str(msg[k]["UserID"])
        except:
            return ""
        return ""

    def extract_lat_lon_any_position(data):
        msg = data.get("Message", {})
        # try multiple position-like blocks
        for k in ("PositionReport", "StandardClassBPositionReport", "ExtendedClassBPositionReport", "BaseStationReport"):
            if k in msg:
                blk = msg[k]
                if "Latitude" in blk and "Longitude" in blk:
                    return float(blk["Latitude"]), float(blk["Longitude"])
        # fallback: metadata
        meta = data.get("MetaData") or data.get("Metadata") or {}
        if "latitude" in meta and "longitude" in meta:
            return float(meta["latitude"]), float(meta["longitude"])
        raise KeyError("No lat/lon found")

    # ------- websocket callbacks -------
    def on_open(ws):
        nonlocal opened, subsent
        opened = True

        sub = {
            "APIKey": API_KEY,
            "BoundingBoxes": ALL_BOXES,
            # ✅ وسّع الأنواع حتى ما نفقد رسائل Position
            "FilterMessageTypes": [
                "PositionReport",
                "StandardClassBPositionReport",
                "ExtendedClassBPositionReport",
                "BaseStationReport",
                "ShipStaticData",
            ],
        }
        ws.send(json.dumps(sub))
        subsent = True
        print("Subscribed.")

    def on_message(ws, message):
        nonlocal samples_total, samples_pos, samples_static, pos_hits_red, pos_hits_gulf, last_error
        samples_total += 1

        # if server sends plain error text
        if isinstance(message, str) and '"error"' in message:
            last_error = message
            print("SERVER ERROR:", message)
            return

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
                    if mmsi in seen_red and is_oil_tanker(vtype):
                        oil_red.add(mmsi)
                    if mmsi in seen_gulf and is_oil_tanker(vtype):
                        oil_gulf.add(mmsi)
            except:
                pass
            return

        # any position-like type
        if mt in ("PositionReport", "StandardClassBPositionReport", "ExtendedClassBPositionReport", "BaseStationReport"):
            samples_pos += 1
            try:
                lat, lon = extract_lat_lon_any_position(data)
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
        nonlocal last_error
        last_error = str(error)
        print("WS ERROR:", error)

    def on_close(ws, code, reason):
        nonlocal close_code, close_reason
        close_code = code
        close_reason = reason or ""
        print("WS CLOSED:", code, reason)

    ws = websocket.WebSocketApp(
        "wss://stream.aisstream.io/v0/stream",
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )

    timer = threading.Timer(CAPTURE_SECONDS, lambda: ws.close())
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
        "last_error": last_error,
        "close_code": close_code,
        "close_reason": close_reason,
    }

if __name__ == "__main__":
    attempts = 0
    result = None

    for i in range(RETRY_ON_ZERO + 1):
        attempts += 1
        result = run_capture_once()
        if result["samples_total"] > 0:
            break
        time.sleep(20)

    if result["samples_total"] == 0:
        send_telegram(build_diag(
            opened=result["opened"],
            close_code=result["close_code"],
            close_reason=result["close_reason"],
            last_error=result["last_error"],
            attempts=attempts,
            subsent=result["subsent"]
        ))
    else:
        send_telegram(build_report(
            result["samples_total"],
            result["samples_pos"],
            result["samples_static"],
            result["seen_red"],
            result["seen_gulf"],
            result["oil_red"],
            result["oil_gulf"],
            result["pos_hits_red"],
            result["pos_hits_gulf"],
        ))

    print("Done.")
