import os
import json
import time
import threading
import datetime
import requests
import websocket
from typing import Dict, List, Tuple

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
# Capture window (B = hourly; but capture a few minutes each run)
# =========================
CAPTURE_SECONDS = 180  # 3 minutes (أفضل بكثير من 60)

# =========================
# Bounding Boxes (smaller, coastal KSA focus)
# Format: [[lat1, lon1], [lat2, lon2]]
# =========================
RED_SEA_BOXES: List[List[List[float]]] = [
    # جنوب/وسط الساحل (قريب جدة/ينبع تقريبًا)
    [[19.0, 37.0], [24.0, 41.5]],
    # شمال الساحل (قريب ضباء/تبوك الساحلية)
    [[24.0, 35.0], [29.5, 39.5]],
    # مدخل الجنوب (تقريبًا باتجاه جازان/الحدود الجنوبية الغربية)
    [[16.0, 40.0], [19.0, 43.5]],
]

GULF_BOXES: List[List[List[float]]] = [
    # الخليج (قريب الدمام/الجبيل/رأس تنورة)
    [[24.0, 48.0], [29.5, 52.5]],
    # امتداد شمالي شرقي بسيط
    [[26.0, 50.5], [30.5, 55.5]],
]

ALL_BOXES = RED_SEA_BOXES + GULF_BOXES

# =========================
# Type cache (persist)
# =========================
TYPE_CACHE_FILE = "ais_type_cache.json"
mmsi_to_type: Dict[str, int] = {}

def load_type_cache():
    global mmsi_to_type
    try:
        with open(TYPE_CACHE_FILE, "r", encoding="utf-8") as f:
            mmsi_to_type = {str(k): int(v) for k, v in json.load(f).items()}
    except Exception:
        mmsi_to_type = {}

def save_type_cache():
    try:
        with open(TYPE_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(mmsi_to_type, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Could not save type cache:", e)

# =========================
# Helpers
# =========================
def normalize_box(box: List[List[float]]) -> Tuple[float, float, float, float]:
    (lat1, lon1), (lat2, lon2) = box
    min_lat, max_lat = (lat1, lat2) if lat1 <= lat2 else (lat2, lat1)
    min_lon, max_lon = (lon1, lon2) if lon1 <= lon2 else (lon2, lon1)
    return min_lat, max_lat, min_lon, max_lon

def in_box(lat: float, lon: float, box: List[List[float]]) -> bool:
    min_lat, max_lat, min_lon, max_lon = normalize_box(box)
    return (min_lat <= lat <= max_lat) and (min_lon <= lon <= max_lon)

def in_any(lat: float, lon: float, boxes: List[List[List[float]]]) -> bool:
    return any(in_box(lat, lon, b) for b in boxes)

def is_oil_tanker(ais_type: int) -> bool:
    # AIS type 80-89 (Tankers)
    try:
        t = int(ais_type)
    except Exception:
        t = 0
    return 80 <= t <= 89

def send_telegram(text: str):
    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    r = requests.post(url, json={"chat_id": CHAT_ID, "text": text}, timeout=25)
    print("TELEGRAM STATUS:", r.status_code)
    print("TELEGRAM RESPONSE:", r.text)
    r.raise_for_status()

# =========================
# Counters (unique by MMSI)
# =========================
seen_red = set()
seen_gulf = set()

samples_total = 0
samples_pos = 0
samples_static = 0

def extract_mmsi(data: dict) -> str:
    meta = data.get("MetaData") or data.get("Metadata") or {}
    mmsi = meta.get("MMSI") or meta.get("mmsi")
    if mmsi:
        return str(mmsi)

    # fallback from message payload
    mt = data.get("MessageType")
    try:
        if mt == "PositionReport":
            return str(data["Message"]["PositionReport"]["UserID"])
        if mt == "ShipStaticData":
            return str(data["Message"]["ShipStaticData"]["UserID"])
    except Exception:
        return ""
    return ""

def extract_lat_lon_from_position(data: dict) -> Tuple[float, float]:
    # primary
    pr = data["Message"]["PositionReport"]
    return float(pr["Latitude"]), float(pr["Longitude"])

# =========================
# WebSocket handlers
# =========================
def on_message(ws, message):
    global samples_total, samples_pos, samples_static
    samples_total += 1

    try:
        data = json.loads(message)
    except Exception:
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
        except Exception:
            pass
        return

    if mt == "PositionReport":
        samples_pos += 1
        try:
            lat, lon = extract_lat_lon_from_position(data)
        except Exception:
            return

        # classify which area
        if in_any(lat, lon, RED_SEA_BOXES):
            seen_red.add(mmsi)
        if in_any(lat, lon, GULF_BOXES):
            seen_gulf.add(mmsi)

def on_error(ws, error):
    print("WS ERROR:", error)

def on_close(ws, code, msg):
    print("WS CLOSED:", code, msg)

def on_open(ws):
    sub = {
        "APIKey": API_KEY,
        "BoundingBoxes": ALL_BOXES,
        "FilterMessageTypes": ["PositionReport", "ShipStaticData"]
    }
    ws.send(json.dumps(sub))
    print("Subscribed.")

def run_capture(seconds: int):
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

════════════════════
📍 ملاحظات تشغيلية:
• إذا كان ShipStaticData قليل، عدّ ناقلات النفط قد يطلع 0 مؤقتًا.
• الكاش يُحسّن الدقة تدريجيًا مع كل ساعة تشغيل.
"""

if __name__ == "__main__":
    load_type_cache()

    try:
        run_capture(CAPTURE_SECONDS)
    except Exception as e:
        print("Capture exception:", e)

    save_type_cache()
    send_telegram(build_report())
    print("AIS report sent.")
