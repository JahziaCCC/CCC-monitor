import os
import json
import threading
import datetime
import time
import requests
import websocket

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
API_KEY = os.environ["AISSTREAM_API_KEY"]

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
now = datetime.datetime.now(KSA_TZ)

CAPTURE_SECONDS = 180  # 3 minutes each hourly run

# =========================
# Areas
# =========================
RED_SEA_BOXES = [
    [[12.0, 41.0], [29.8, 44.5]]
]
GULF_BOXES = [
    [[22.0, 47.0], [31.5, 57.0]]
]
ALL_BOXES = RED_SEA_BOXES + GULF_BOXES

# =========================
# Files (persist in repo workspace)
# =========================
TYPE_CACHE_FILE = "ais_type_cache.json"
STATE_FILE = "ais_state.json"

# =========================
# Thresholds (tweak anytime)
# =========================
SPIKE_SHIPS_DELTA = 25         # if total ships jump by >= 25 vs last run -> alert
SPIKE_TANKERS_DELTA = 6        # if oil tankers jump by >= 6 -> alert

def send_telegram(text: str):
    requests.post(
        f"https://api.telegram.org/bot{BOT}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text},
        timeout=20
    )

def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path, obj):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def normalize_box(box):
    (lat1, lon1), (lat2, lon2) = box
    return min(lat1, lat2), max(lat1, lat2), min(lon1, lon2), max(lon1, lon2)

def in_box(lat, lon, box):
    a, b, c, d = normalize_box(box)
    return a <= lat <= b and c <= lon <= d

def in_any(lat, lon, boxes):
    return any(in_box(lat, lon, b) for b in boxes)

def is_oil_tanker(vtype):
    try:
        v = int(vtype)
    except Exception:
        v = 0
    return 80 <= v <= 89

def extract_mmsi(data):
    meta = data.get("MetaData") or data.get("Metadata") or {}
    m = meta.get("MMSI") or meta.get("mmsi")
    if m:
        return str(m)

    msg = data.get("Message", {})
    for k, blk in msg.items():
        if isinstance(blk, dict) and "UserID" in blk:
            return str(blk["UserID"])
    return ""

def extract_lat_lon_and_block(data):
    msg = data.get("Message", {})
    for _, blk in msg.items():
        if isinstance(blk, dict) and ("Latitude" in blk) and ("Longitude" in blk):
            return float(blk["Latitude"]), float(blk["Longitude"]), blk
    raise KeyError

def calculate_risk(gulf_count, red_count, oil_total):
    risk = 0

    # 1) Gulf traffic weight
    if gulf_count > 60:
        risk += 45
    elif gulf_count > 30:
        risk += 30
    else:
        risk += 15

    # 2) Oil tankers weight
    risk += min(oil_total * 6, 35)

    # 3) Red Sea coverage penalty (awareness)
    if red_count == 0:
        risk += 10

    risk = min(risk, 100)

    if risk >= 70:
        level = "🔴 مرتفع"
    elif risk >= 40:
        level = "🟠 متوسط"
    else:
        level = "🟢 منخفض"

    return risk, level

def run_capture():
    # persistent type cache
    mmsi_to_type = load_json(TYPE_CACHE_FILE, {})
    # runtime sets
    seen_red, seen_gulf = set(), set()
    oil_red, oil_gulf = set(), set()

    samples_total = 0
    samples_pos = 0
    samples_static = 0

    def on_open(ws):
        ws.send(json.dumps({
            "APIKey": API_KEY,
            "BoundingBoxes": ALL_BOXES
        }))

    def on_message(ws, message):
        nonlocal samples_total, samples_pos, samples_static
        samples_total += 1

        # ignore non-json
        try:
            data = json.loads(message)
        except Exception:
            return

        mmsi = extract_mmsi(data)
        if not mmsi:
            return

        mt = data.get("MessageType")

        # Ship static -> cache type
        if mt == "ShipStaticData":
            samples_static += 1
            try:
                vtype = int(data["Message"]["ShipStaticData"].get("Type", 0))
                if vtype:
                    mmsi_to_type[mmsi] = vtype
            except Exception:
                pass
            return

        # Position-like (anything with lat/lon)
        try:
            lat, lon, blk = extract_lat_lon_and_block(data)
        except Exception:
            return

        samples_pos += 1

        # type may be inside blk, otherwise from cache
        vtype = blk.get("Type", 0)
        if not vtype:
            vtype = mmsi_to_type.get(mmsi, 0)

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
    ws.run_forever(ping_interval=20, ping_timeout=10)
    timer.cancel()

    # save cache
    save_json(TYPE_CACHE_FILE, mmsi_to_type)

    return {
        "samples_total": samples_total,
        "samples_pos": samples_pos,
        "samples_static": samples_static,
        "red": seen_red,
        "gulf": seen_gulf,
        "oil_red": oil_red,
        "oil_gulf": oil_gulf
    }

if __name__ == "__main__":
    res = run_capture()

    red_count = len(res["red"])
    gulf_count = len(res["gulf"])
    oil_total = len(res["oil_red"]) + len(res["oil_gulf"])

    risk, level = calculate_risk(gulf_count, red_count, oil_total)

    # load previous state to compute deltas + alerts
    prev = load_json(STATE_FILE, {
        "gulf_count": 0,
        "red_count": 0,
        "oil_total": 0,
        "risk": 0,
        "ts": ""
    })

    d_gulf = gulf_count - int(prev.get("gulf_count", 0))
    d_red = red_count - int(prev.get("red_count", 0))
    d_oil = oil_total - int(prev.get("oil_total", 0))
    d_risk = risk - int(prev.get("risk", 0))

    # save current state
    save_json(STATE_FILE, {
        "gulf_count": gulf_count,
        "red_count": red_count,
        "oil_total": oil_total,
        "risk": risk,
        "ts": now.strftime("%Y-%m-%d %H:%M")
    })

    # human-friendly Red Sea status
    if red_count == 0:
        red_text = "⚠️ تغطية AIS ضعيفة"
    else:
        red_text = str(red_count)

    # main report
    msg = f"""🚢 تقرير الحركة البحرية الذكي (CCC)
🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA

════════════════════
📡 الرسائل: {res['samples_total']}
📍 Position: {res['samples_pos']} | Static: {res['samples_static']}

📊 السفن:
• البحر الأحمر: {red_text} (Δ {d_red:+})
• الخليج العربي: {gulf_count} (Δ {d_gulf:+})

🛢️ ناقلات النفط (80–89):
• الإجمالي: {oil_total} (Δ {d_oil:+})

════════════════════
📊 مؤشر المخاطر البحري:
{risk}/100 — {level} (Δ {d_risk:+})

📌 تفسير سريع:
• كثافة الخليج + ناقلات النفط + حالة تغطية البحر الأحمر.
"""

    send_telegram(msg)

    # alerts (separate message only when needed)
    spike_alerts = []
    if d_gulf >= SPIKE_SHIPS_DELTA:
        spike_alerts.append(f"🚨 ارتفاع مفاجئ في سفن الخليج: +{d_gulf}")
    if d_oil >= SPIKE_TANKERS_DELTA:
        spike_alerts.append(f"🛢️ زيادة ناقلات النفط: +{d_oil}")

    if spike_alerts:
        alert_msg = "🚨 تنبيه بحري (Early Warning)\n" + "\n".join(spike_alerts) + f"\n🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA"
        send_telegram(alert_msg)
