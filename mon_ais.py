import os
import json
import threading
import datetime
import time
import requests
import websocket

BOT = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
API_KEY = os.environ.get("AISSTREAM_API_KEY", "").strip()

if not BOT:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN secret")
if not CHAT_ID:
    raise RuntimeError("Missing TELEGRAM_CHAT_ID secret")
if not API_KEY:
    raise RuntimeError("Missing AISSTREAM_API_KEY secret")

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
now = datetime.datetime.now(KSA_TZ)

CAPTURE_SECONDS = 180
RETRY_ON_ZERO = 1  # محاولة إضافية واحدة
GLOBAL_TEST_SECONDS = 20  # اختبار عالمي سريع

RED_SEA_BOXES = [
    [[16.2, 41.0], [18.5, 43.5]],
    [[20.0, 38.0], [22.8, 40.8]],
    [[23.0, 37.0], [25.5, 39.8]],
    [[26.0, 35.0], [29.2, 38.6]],
]
GULF_BOXES = [
    [[24.0, 48.0], [28.7, 51.8]],
    [[26.8, 50.8], [30.5, 55.5]],
]
ALL_BOXES = RED_SEA_BOXES + GULF_BOXES
GLOBAL_BOX = [[-90.0, -180.0], [90.0, 180.0]]

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

def run_capture(boxes, seconds):
    # state
    samples_total = 0
    samples_pos_any = 0
    samples_static = 0

    seen_red, seen_gulf = set(), set()
    oil_red, oil_gulf = set(), set()

    mmsi_to_type = {}

    opened = False
    subsent = False
    last_error = ""
    close_code = None
    close_reason = ""

    pos_hits_red = 0
    pos_hits_gulf = 0

    def on_open(ws):
        nonlocal opened, subsent
        opened = True

        # ✅ بدون FilterMessageTypes (اختياري) لتجنب فقدان الدفق
        sub = {
            "APIKey": API_KEY,
            "BoundingBoxes": boxes,
        }
        # AISStream يشير أن الرسالة تُرسل فور فتح الاتصال.  [oai_citation:3‡aisstream.io](https://aisstream.io/documentation)
        ws.send(json.dumps(sub))
        subsent = True
        print("Subscribed (no filters).")

    def on_message(ws, message):
        nonlocal samples_total, samples_pos_any, samples_static, last_error
        nonlocal pos_hits_red, pos_hits_gulf
        samples_total += 1

        if isinstance(message, str) and '"error"' in message:
            last_error = message
            print("SERVER ERROR:", message)
            return

        try:
            data = json.loads(message)
        except:
            return

        mmsi = extract_mmsi(data)
        if not mmsi:
            return

        mt = data.get("MessageType")

        # ShipStaticData: خزّن النوع
        if mt == "ShipStaticData":
            samples_static += 1
            try:
                s = data["Message"]["ShipStaticData"]
                vtype = int(s.get("Type", 0))
                if vtype:
                    mmsi_to_type[mmsi] = vtype
            except:
                pass
            return

        # أي رسالة فيها Lat/Lon تعتبر Position-like
        try:
            lat, lon, blk = extract_lat_lon_any(data)
        except:
            return

        samples_pos_any += 1

        # نوع السفينة قد يظهر داخل بعض رسائل الـ Position نفسها (مثل ExtendedClassBPositionReport فيها Type)  [oai_citation:4‡aisstream.io](https://aisstream.io/documentation)
        vtype = 0
        if isinstance(blk, dict) and "Type" in blk:
            try:
                vtype = int(blk.get("Type", 0))
            except:
                vtype = 0
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

    timer = threading.Timer(seconds, lambda: ws.close())
    timer.start()
    ws.run_forever(ping_interval=20, ping_timeout=10)
    timer.cancel()

    return {
        "opened": opened,
        "subsent": subsent,
        "samples_total": samples_total,
        "samples_pos_any": samples_pos_any,
        "samples_static": samples_static,
        "seen_red": seen_red,
        "seen_gulf": seen_gulf,
        "oil_red": oil_red,
        "oil_gulf": oil_gulf,
        "pos_hits_red": pos_hits_red,
        "pos_hits_gulf": pos_hits_gulf,
        "close_code": close_code,
        "close_reason": close_reason,
        "last_error": last_error,
    }

def report_text(res, label):
    return f"""🚢 تقرير الحركة البحرية – البحر الأحمر والخليج العربي ({label})
🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA

════════════════════
📡 نافذة الالتقاط: {res["samples_total"]} رسالة (≈ {CAPTURE_SECONDS} ثانية)
• Any-Position: {res["samples_pos_any"]}
• ShipStaticData: {res["samples_static"]}

📊 إجمالي السفن (فريدة):
• البحر الأحمر: {len(res["seen_red"])}
• الخليج العربي: {len(res["seen_gulf"])}

🛢️ ناقلات النفط (80–89):
• البحر الأحمر: {len(res["oil_red"])}
• الخليج العربي: {len(res["oil_gulf"])}

════════════════════
🔎 Position hits:
• Red Sea: {res["pos_hits_red"]}
• Gulf: {res["pos_hits_gulf"]}
"""

def diag_text(main_res, global_res, attempts):
    return f"""⚠️ AISStream تشخيص
🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA

• attempts: {attempts}
• opened: {main_res["opened"]}
• subscription_sent: {main_res["subsent"]}
• last_error: {main_res["last_error"] or "N/A"}

📌 نتيجة الاختبار العالمي (20s):
• global_messages: {global_res["samples_total"]}
• global_any_position: {global_res["samples_pos_any"]}

✅ تفسير سريع:
- إذا global_messages > 0: الخدمة شغالة لكن نافذة/تغطية منطقتنا ما أعطت بيانات الآن.
- إذا global_messages = 0: غالبًا Throttle/انقطاع مؤقت أو مشكلة في الخدمة/المفتاح.  [oai_citation:5‡aisstream.io](https://aisstream.io/documentation)
"""

if __name__ == "__main__":
    attempts = 0
    res = None

    for _ in range(RETRY_ON_ZERO + 1):
        attempts += 1
        res = run_capture(ALL_BOXES, CAPTURE_SECONDS)
        if res["samples_total"] > 0:
            break
        time.sleep(20)

    if res["samples_total"] > 0:
        send_telegram(report_text(res, "LIVE"))
    else:
        # Global health check
        global_res = run_capture([GLOBAL_BOX], GLOBAL_TEST_SECONDS)
        send_telegram(diag_text(res, global_res, attempts))
