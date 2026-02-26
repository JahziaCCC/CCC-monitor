import os
import json
import math
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

CAPTURE_SECONDS = 180
GLOBAL_TEST_SECONDS = 20

TYPE_CACHE_FILE = "ais_type_cache.json"
STATE_FILE = "ais_ports_state.json"

WAITING_SPEED_KTS = 0.7
ALERT_WAITING_SPIKE = 8

# حجم الصندوق حول كل ميناء/محطة (كم)
BOX_RADIUS_KM = 180  # وسّعناه أكثر عشان يشمل مناطق الانتظار offshore

# =========================
# Ports + Oil Terminals (KSA)
# =========================
SITES = {
    # Red Sea
    "ميناء جدة الإسلامي": {"lat": 21.484, "lon": 39.173},
    "ميناء الملك عبدالله (KAEC)": {"lat": 22.523, "lon": 39.089},
    "ميناء ينبع التجاري": {"lat": 24.0665, "lon": 38.0675},
    "ميناء جازان": {"lat": 16.9189, "lon": 42.5573},
    "ميناء ضباء": {"lat": 27.5606, "lon": 35.5440},

    # Gulf
    "ميناء الملك عبدالعزيز (الدمام)": {"lat": 26.4410, "lon": 50.1485},
    "ميناء الجبيل التجاري": {"lat": 27.0241, "lon": 49.6793},

    # Oil terminals
    "محطة نفط رأس تنورة": {"lat": 26.6726, "lon": 50.1219},
    "محطة نفط الجعيمة (Juaymah)": {"lat": 26.93, "lon": 50.06},
    "محطة نفط تناجيب (Tanajib)": {"lat": 27.7948, "lon": 48.8921},
}

def send_telegram(text: str):
    requests.post(
        f"https://api.telegram.org/bot{BOT}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text},
        timeout=25
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

def km_to_deg_lat(km: float) -> float:
    return km / 111.0

def km_to_deg_lon(km: float, lat: float) -> float:
    c = math.cos(math.radians(lat))
    if c < 0.2:
        c = 0.2
    return km / (111.0 * c)

def make_box(lat, lon, radius_km):
    dlat = km_to_deg_lat(radius_km)
    dlon = km_to_deg_lon(radius_km, lat)
    return [[lat - dlat, lon - dlon], [lat + dlat, lon + dlon]]

def normalize_box(box):
    (lat1, lon1), (lat2, lon2) = box
    return min(lat1, lat2), max(lat1, lat2), min(lon1, lon2), max(lon1, lon2)

def in_box(lat, lon, box):
    a, b, c, d = normalize_box(box)
    return a <= lat <= b and c <= lon <= d

def extract_mmsi(data):
    meta = data.get("MetaData") or data.get("Metadata") or {}
    m = meta.get("MMSI") or meta.get("mmsi")
    if m:
        return str(m)
    msg = data.get("Message", {})
    for _, blk in msg.items():
        if isinstance(blk, dict) and "UserID" in blk:
            return str(blk["UserID"])
    return ""

def extract_lat_lon(data):
    meta = data.get("MetaData") or data.get("Metadata") or {}
    if "latitude" in meta and "longitude" in meta:
        return float(meta["latitude"]), float(meta["longitude"])
    msg = data.get("Message", {})
    for _, blk in msg.items():
        if isinstance(blk, dict) and "Latitude" in blk and "Longitude" in blk:
            return float(blk["Latitude"]), float(blk["Longitude"])
    raise KeyError

def get_nav_status(data):
    msg = data.get("Message", {})
    for _, blk in msg.items():
        if isinstance(blk, dict):
            for k in ("NavigationalStatus", "NavStatus", "NavigationStatus"):
                if k in blk:
                    try:
                        return int(blk[k])
                    except Exception:
                        pass
    return None

def get_sog_knots(data):
    msg = data.get("Message", {})
    for _, blk in msg.items():
        if isinstance(blk, dict):
            for k in ("Sog", "SOG", "SpeedOverGround", "Speed"):
                if k in blk:
                    try:
                        return float(blk[k])
                    except Exception:
                        pass
    return None

def is_waiting(data):
    nav = get_nav_status(data)
    if nav in (1, 5):  # anchored/moored
        return True
    sog = get_sog_knots(data)
    if sog is not None and sog <= WAITING_SPEED_KTS:
        return True
    return False

def is_oil_tanker(vtype):
    try:
        v = int(vtype)
    except Exception:
        v = 0
    return 80 <= v <= 89

def level(total, waiting):
    if waiting >= 15 or total >= 60:
        return "🔴 شديد"
    if waiting >= 7 or total >= 30:
        return "🟠 مرتفع"
    if waiting >= 3 or total >= 12:
        return "🟡 متوسط"
    return "🟢 منخفض"

def run_stream_for_boxes(boxes, seconds, type_cache, collect_ports=False, port_boxes=None, port_names=None):
    samples_total = 0
    samples_pos = 0
    samples_static = 0

    opened = False
    subsent = False
    close_code = None
    close_reason = None
    last_error = None

    # per-port unique MMSI sets
    ships = {n: set() for n in (port_names or [])}
    waiting = {n: set() for n in (port_names or [])}
    tankers = {n: set() for n in (port_names or [])}

    def on_open(ws):
        nonlocal opened, subsent
        opened = True
        ws.send(json.dumps({"APIKey": API_KEY, "BoundingBoxes": boxes}))
        subsent = True

    def on_error(ws, err):
        nonlocal last_error
        last_error = str(err)

    def on_close(ws, code, reason):
        nonlocal close_code, close_reason
        close_code = code
        close_reason = reason

    def on_message(ws, message):
        nonlocal samples_total, samples_pos, samples_static, last_error
        samples_total += 1

        try:
            data = json.loads(message)
        except Exception:
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
                    type_cache[mmsi] = vtype
            except Exception:
                pass
            return

        try:
            lat, lon = extract_lat_lon(data)
        except Exception:
            return

        samples_pos += 1

        if not collect_ports:
            return

        # check which port box it falls into (can be multiple)
        for name, box in zip(port_names, port_boxes):
            if in_box(lat, lon, box):
                ships[name].add(mmsi)
                if is_waiting(data):
                    waiting[name].add(mmsi)
                vtype = type_cache.get(mmsi, 0)
                if is_oil_tanker(vtype):
                    tankers[name].add(mmsi)

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
        "samples_total": samples_total,
        "samples_pos": samples_pos,
        "samples_static": samples_static,
        "opened": opened,
        "subsent": subsent,
        "close_code": close_code,
        "close_reason": close_reason,
        "last_error": last_error,
        "ships": {k: len(v) for k, v in ships.items()},
        "waiting": {k: len(v) for k, v in waiting.items()},
        "tankers": {k: len(v) for k, v in tankers.items()},
    }

if __name__ == "__main__":
    type_cache = load_json(TYPE_CACHE_FILE, {})
    prev_state = load_json(STATE_FILE, {"ports": {}, "ts": ""})

    # build port boxes list
    port_names = list(SITES.keys())
    port_boxes = [make_box(SITES[n]["lat"], SITES[n]["lon"], BOX_RADIUS_KM) for n in port_names]

    # 1) main capture for ports
    res = run_stream_for_boxes(
        boxes=port_boxes,
        seconds=CAPTURE_SECONDS,
        type_cache=type_cache,
        collect_ports=True,
        port_boxes=port_boxes,
        port_names=port_names
    )

    # if 0 messages -> do global test
    global_res = None
    if res["samples_total"] == 0:
        global_box = [[-90.0, -180.0], [90.0, 180.0]]
        global_res = run_stream_for_boxes(
            boxes=[global_box],
            seconds=GLOBAL_TEST_SECONDS,
            type_cache=type_cache,
            collect_ports=False
        )

    save_json(TYPE_CACHE_FILE, type_cache)

    # build report lines
    lines = []
    alerts = []
    hits_sites = 0

    for name in port_names:
        total = res["ships"].get(name, 0)
        wait = res["waiting"].get(name, 0)
        tnk = res["tankers"].get(name, 0)

        prev = (prev_state.get("ports", {}).get(name) or {})
        d_wait = wait - int(prev.get("waiting", 0))
        d_total = total - int(prev.get("total", 0))

        if total > 0:
            hits_sites += 1
            lvl = level(total, wait)
            lines.append(f"{lvl} {name}\n• إجمالي ضمن ~{BOX_RADIUS_KM}كم: {total} (Δ {d_total:+}) | منتظرة/راسية: {wait} (Δ {d_wait:+}) | ناقلات: {tnk}")
        else:
            lines.append(f"⚠️ {name}\n• لا توجد بيانات AIS ضمن نطاق ~{BOX_RADIUS_KM}كم خلال النافذة")

        if d_wait >= ALERT_WAITING_SPIKE and wait >= 5:
            alerts.append(f"🚨 ازدحام متصاعد في {name}: +{d_wait} سفن منتظرة")

    # save state
    save_json(STATE_FILE, {
        "ports": {n: {"total": res["ships"].get(n,0), "waiting": res["waiting"].get(n,0), "tankers": res["tankers"].get(n,0)} for n in port_names},
        "ts": now.strftime("%Y-%m-%d %H:%M")
    })

    diag = f"""🔎 تشخيص اتصال
• opened: {res['opened']}
• subscription_sent: {res['subsent']}
• close_code: {res['close_code']}
• close_reason: {res['close_reason'] or 'N/A'}
• last_error: {res['last_error'] or 'N/A'}
"""

    if global_res is not None:
        diag += f"""
🌍 اختبار عالمي ({GLOBAL_TEST_SECONDS}s):
• global_messages: {global_res['samples_total']}
• global_position: {global_res['samples_pos']}
"""

    header = f"""⚓ تقرير ازدحام موانئ المملكة + محطات النفط (Single Connection)
🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA

════════════════════
📡 نافذة الالتقاط: {CAPTURE_SECONDS}s
• messages: {res['samples_total']}
• position: {res['samples_pos']}
• static: {res['samples_static']}
• sites with hits: {hits_sites}/{len(SITES)}

════════════════════
{diag}
════════════════════
"""

    send_telegram(header + "\n".join([""] + [("—"*0)] ) + "\n\n".join(lines))

    if alerts:
        send_telegram("🚨 تنبيهات ازدحام (Port Congestion)\n" + "\n".join(alerts) + f"\n🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA")
