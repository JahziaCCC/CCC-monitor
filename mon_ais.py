import os
import json
import math
import threading
import datetime
import requests
import websocket

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
API_KEY = os.environ["AISSTREAM_API_KEY"]

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
now = datetime.datetime.now(KSA_TZ)

CAPTURE_SECONDS = 180  # 3 minutes

# صندوق يغطي البحر الأحمر + الخليج + سواحل المملكة
SAUDI_REGION_BOX = [[10.0, 32.0], [32.5, 58.5]]  # [[lat,lon],[lat,lon]]

STATE_FILE = "ais_ports_state.json"
TYPE_CACHE_FILE = "ais_type_cache.json"

WAITING_SPEED_KTS = 0.7
ALERT_WAITING_SPIKE = 8

# ====== نطاق الازدحام حول الميناء/المحطة (km) ======
CONGESTION_RADIUS_KM = 120  # واسع ويشمل مناطق الانتظار offshore

# =========================
# Ports + Oil Terminals (KSA)
# =========================
PORTS = {
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

def send_telegram(text: str):
    requests.post(
        f"https://api.telegram.org/bot{BOT}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text},
        timeout=25
    )

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(a))

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

def extract_lat_lon_and_block(data):
    # 1) try Message blocks
    msg = data.get("Message", {})
    for _, blk in msg.items():
        if isinstance(blk, dict) and ("Latitude" in blk) and ("Longitude" in blk):
            return float(blk["Latitude"]), float(blk["Longitude"]), blk

    # 2) fallback to metadata
    meta = data.get("MetaData") or data.get("Metadata") or {}
    if ("latitude" in meta) and ("longitude" in meta):
        return float(meta["latitude"]), float(meta["longitude"]), {}

    raise KeyError("No lat/lon")

def get_sog_knots(blk: dict):
    for k in ("Sog", "SOG", "SpeedOverGround", "Speed"):
        if k in blk:
            try:
                return float(blk[k])
            except Exception:
                pass
    return None

def get_nav_status(blk: dict):
    for k in ("NavigationalStatus", "NavStatus", "NavigationStatus"):
        if k in blk:
            try:
                return int(blk[k])
            except Exception:
                pass
    return None

def is_waiting(blk: dict):
    nav = get_nav_status(blk)
    sog = get_sog_knots(blk)
    if nav in (1, 5):  # anchored / moored (شائع)
        return True
    if sog is not None and sog <= WAITING_SPEED_KTS:
        return True
    return False

def is_oil_tanker(vtype):
    try:
        v = int(vtype)
    except Exception:
        v = 0
    return 80 <= v <= 89

def congestion_level(total, waiting):
    if waiting >= 20 or total >= 80:
        return "🔴 شديد"
    if waiting >= 10 or total >= 40:
        return "🟠 مرتفع"
    if waiting >= 4 or total >= 15:
        return "🟡 متوسط"
    return "🟢 منخفض"

def nearest_port(lat, lon):
    best_name = None
    best_d = 10**9
    for name, p in PORTS.items():
        d = haversine_km(p["lat"], p["lon"], lat, lon)
        if d < best_d:
            best_d = d
            best_name = name
    return best_name, best_d

def run_capture():
    type_cache = load_json(TYPE_CACHE_FILE, {})  # mmsi -> type

    samples_total = 0
    samples_pos = 0
    samples_static = 0
    valid_latlon = 0

    # track unique vessels (last position in window)
    vessels = {}  # mmsi -> {"lat","lon","waiting","type"}

    # track min/max for diagnostics
    min_lat = 999
    max_lat = -999
    min_lon = 999
    max_lon = -999

    def on_open(ws):
        ws.send(json.dumps({
            "APIKey": API_KEY,
            "BoundingBoxes": [SAUDI_REGION_BOX]
        }))

    def on_message(ws, message):
        nonlocal samples_total, samples_pos, samples_static, valid_latlon
        nonlocal min_lat, max_lat, min_lon, max_lon

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
            lat, lon, blk = extract_lat_lon_and_block(data)
        except Exception:
            return

        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return

        valid_latlon += 1
        samples_pos += 1

        min_lat = min(min_lat, lat)
        max_lat = max(max_lat, lat)
        min_lon = min(min_lon, lon)
        max_lon = max(max_lon, lon)

        vtype = 0
        if isinstance(blk, dict) and "Type" in blk:
            try:
                vtype = int(blk.get("Type", 0))
            except Exception:
                vtype = 0
        if not vtype:
            vtype = type_cache.get(mmsi, 0)

        vessels[mmsi] = {
            "lat": lat,
            "lon": lon,
            "waiting": is_waiting(blk) if isinstance(blk, dict) else False,
            "type": vtype
        }

    ws = websocket.WebSocketApp(
        "wss://stream.aisstream.io/v0/stream",
        on_open=on_open,
        on_message=on_message
    )

    timer = threading.Timer(CAPTURE_SECONDS, lambda: ws.close())
    timer.start()
    ws.run_forever(ping_interval=20, ping_timeout=10)
    timer.cancel()

    save_json(TYPE_CACHE_FILE, type_cache)

    diag = {
        "min_lat": None if valid_latlon == 0 else round(min_lat, 4),
        "max_lat": None if valid_latlon == 0 else round(max_lat, 4),
        "min_lon": None if valid_latlon == 0 else round(min_lon, 4),
        "max_lon": None if valid_latlon == 0 else round(max_lon, 4),
    }

    return samples_total, samples_pos, samples_static, valid_latlon, vessels, diag

if __name__ == "__main__":
    prev_state = load_json(STATE_FILE, {"ports": {}, "ts": ""})

    total, pos, stat, valid_latlon, vessels, diag = run_capture()

    # build congestion per port by distance
    ports_now = {}
    near_hits = 0
    nearest_bucket = {"<=50km": 0, "<=120km": 0, ">120km": 0}

    for port in PORTS.keys():
        ports_now[port] = {"total": 0, "waiting": 0, "tankers": 0}

    for mmsi, v in vessels.items():
        name, d = nearest_port(v["lat"], v["lon"])

        if d <= 50:
            nearest_bucket["<=50km"] += 1
        elif d <= CONGESTION_RADIUS_KM:
            nearest_bucket["<=120km"] += 1
        else:
            nearest_bucket[">120km"] += 1

        # count if within congestion radius of ANY port (by nearest)
        if d <= CONGESTION_RADIUS_KM:
            near_hits += 1

        # also attribute vessel to ALL ports within radius (more realistic if overlapping)
        for port_name, p in PORTS.items():
            dd = haversine_km(p["lat"], p["lon"], v["lat"], v["lon"])
            if dd <= CONGESTION_RADIUS_KM:
                ports_now[port_name]["total"] += 1
                if v["waiting"]:
                    ports_now[port_name]["waiting"] += 1
                if is_oil_tanker(v.get("type", 0)):
                    ports_now[port_name]["tankers"] += 1

    # rank by waiting then total
    ranked = sorted(ports_now.items(), key=lambda x: (x[1]["waiting"], x[1]["total"]), reverse=True)

    lines = []
    alerts = []
    for name, v in ranked:
        prev = (prev_state.get("ports", {}).get(name) or {})
        d_wait = v["waiting"] - int(prev.get("waiting", 0))
        d_total = v["total"] - int(prev.get("total", 0))

        lvl = congestion_level(v["total"], v["waiting"])
        lines.append(
            f"{lvl} {name}\n"
            f"• إجمالي ضمن {CONGESTION_RADIUS_KM}كم: {v['total']} (Δ {d_total:+}) | منتظرة/راسية: {v['waiting']} (Δ {d_wait:+}) | ناقلات: {v['tankers']}"
        )

        if d_wait >= ALERT_WAITING_SPIKE and v["waiting"] >= 5:
            alerts.append(f"🚨 ازدحام متصاعد في {name}: +{d_wait} سفن منتظرة")

    save_json(STATE_FILE, {"ports": ports_now, "ts": now.strftime("%Y-%m-%d %H:%M")})

    header = f"""⚓ تقرير ازدحام موانئ المملكة + محطات النفط (Distance)
🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA

════════════════════
📡 رسائل: {total}
📍 Position: {pos} | Static: {stat}

🔎 تشخيص:
• Valid lat/lon: {valid_latlon}
• Vessels unique: {len(vessels)}
• Near ports (<= {CONGESTION_RADIUS_KM}km): {near_hits}
• Nearest port dist: <=50km={nearest_bucket['<=50km']}, <=120km={nearest_bucket['<=120km']}, >120km={nearest_bucket['>120km']}
• Lat/Lon window: lat[{diag['min_lat']},{diag['max_lat']}], lon[{diag['min_lon']},{diag['max_lon']}]

════════════════════
"""

    body = "\n\n".join(lines[:15]) if lines else "لا توجد بيانات ضمن نافذة الالتقاط."
    send_telegram(header + body)

    if alerts:
        send_telegram(
            "🚨 تنبيهات ازدحام (Port Congestion)\n"
            + "\n".join(alerts)
            + f"\n🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA"
        )
