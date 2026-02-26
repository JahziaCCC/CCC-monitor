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

CAPTURE_SECONDS = 180  # 3 دقائق

# =========================
# Saudi region (Red Sea + Gulf) to avoid global flood
# (lat, lon) corners
# =========================
SAUDI_REGION_BOX = [[10.0, 32.0], [32.5, 58.5]]  # جنوب البحر الأحمر إلى الخليج

# =========================
# Ports + Oil Terminals (KSA)
# =========================
PORTS = {
    # Red Sea
    "ميناء جدة الإسلامي": {"lat": 21.484, "lon": 39.173, "radius_km": 25},
    "ميناء الملك عبدالله (KAEC)": {"lat": 22.523, "lon": 39.089, "radius_km": 25},
    "ميناء ينبع التجاري": {"lat": 24.0665, "lon": 38.0675, "radius_km": 22},
    "ميناء جازان": {"lat": 16.9189, "lon": 42.5573, "radius_km": 22},
    "ميناء ضباء": {"lat": 27.5606, "lon": 35.5440, "radius_km": 20},

    # Gulf
    "ميناء الملك عبدالعزيز (الدمام)": {"lat": 26.4410, "lon": 50.1485, "radius_km": 28},
    "ميناء الجبيل التجاري": {"lat": 27.0241, "lon": 49.6793, "radius_km": 28},

    # Oil terminals
    "محطة نفط رأس تنورة": {"lat": 26.6726, "lon": 50.1219, "radius_km": 35},
    "محطة نفط الجعيمة (Juaymah)": {"lat": 26.93, "lon": 50.06, "radius_km": 35},
    "محطة نفط تناجيب (Tanajib)": {"lat": 27.7948, "lon": 48.8921, "radius_km": 35},
}

STATE_FILE = "ais_ports_state.json"
TYPE_CACHE_FILE = "ais_type_cache.json"

ALERT_WAITING_SPIKE = 8
WAITING_SPEED_KTS = 0.7

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
            lat = float(blk["Latitude"])
            lon = float(blk["Longitude"])
            return lat, lon, blk

    # 2) fallback to metadata lat/lon (important!)
    meta = data.get("MetaData") or data.get("Metadata") or {}
    if ("latitude" in meta) and ("longitude" in meta):
        lat = float(meta["latitude"])
        lon = float(meta["longitude"])
        return lat, lon, {}

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
    if nav in (1, 5):  # anchored / moored
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
    if waiting >= 15 or total >= 50:
        return "🔴 شديد"
    if waiting >= 7 or total >= 25:
        return "🟠 مرتفع"
    if waiting >= 3 or total >= 10:
        return "🟡 متوسط"
    return "🟢 منخفض"

def compute_congestion(vessels):
    ports_out = {}
    for pname, p in PORTS.items():
        total = 0
        waiting = 0
        tankers = 0
        for _, v in vessels.items():
            d = haversine_km(p["lat"], p["lon"], v["lat"], v["lon"])
            if d <= p["radius_km"]:
                total += 1
                if v["waiting"]:
                    waiting += 1
                if is_oil_tanker(v.get("type", 0)):
                    tankers += 1
        ports_out[pname] = {"total": total, "waiting": waiting, "tankers": tankers}
    return ports_out

def run_capture():
    type_cache = load_json(TYPE_CACHE_FILE, {})  # mmsi -> type
    vessels = {}  # mmsi -> {lat,lon,waiting,type}

    samples_total = 0
    samples_pos = 0
    samples_static = 0
    valid_latlon = 0
    near_any_hits = 0

    def on_open(ws):
        ws.send(json.dumps({
            "APIKey": API_KEY,
            "BoundingBoxes": [SAUDI_REGION_BOX]
        }))

    def on_message(ws, message):
        nonlocal samples_total, samples_pos, samples_static, valid_latlon, near_any_hits
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

        # ignore invalid coordinates
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return

        valid_latlon += 1
        samples_pos += 1

        # local near-port filter
        near_any = False
        for p in PORTS.values():
            if haversine_km(p["lat"], p["lon"], lat, lon) <= (p["radius_km"] + 8):
                near_any = True
                break
        if not near_any:
            return

        near_any_hits += 1

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
            "type": vtype,
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

    return samples_total, samples_pos, samples_static, valid_latlon, near_any_hits, vessels

if __name__ == "__main__":
    prev_state = load_json(STATE_FILE, {"ports": {}, "ts": ""})

    total, pos, stat, valid_latlon, near_hits, vessels = run_capture()
    ports_now = compute_congestion(vessels)

    ranked = sorted(
        ports_now.items(),
        key=lambda x: (x[1]["waiting"], x[1]["total"]),
        reverse=True
    )

    lines = []
    alerts = []

    for pname, v in ranked:
        lvl = congestion_level(v["total"], v["waiting"])
        prev = (prev_state.get("ports", {}).get(pname) or {})
        d_wait = v["waiting"] - int(prev.get("waiting", 0))
        d_total = v["total"] - int(prev.get("total", 0))

        lines.append(
            f"{lvl} {pname}\n"
            f"• إجمالي: {v['total']} (Δ {d_total:+}) | منتظرة/راسية: {v['waiting']} (Δ {d_wait:+}) | ناقلات: {v['tankers']}"
        )

        if d_wait >= ALERT_WAITING_SPIKE and v["waiting"] >= 5:
            alerts.append(f"🚨 ازدحام متصاعد في {pname}: +{d_wait} سفن منتظرة")

    save_json(STATE_FILE, {"ports": ports_now, "ts": now.strftime("%Y-%m-%d %H:%M")})

    header = f"""⚓ تقرير ازدحام موانئ المملكة + محطات النفط
🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA

════════════════════
📡 رسائل: {total}
📍 Position: {pos} | Static: {stat}

🔎 تشخيص مهم:
• Valid lat/lon: {valid_latlon}
• Near ports hits: {near_hits}
• Vessels tracked: {len(vessels)}

════════════════════
"""

    body = "\n\n".join(lines[:15]) if lines else "لا توجد بيانات قرب الموانئ/المحطات ضمن نافذة الالتقاط."
    send_telegram(header + body)

    if alerts:
        send_telegram(
            "🚨 تنبيهات ازدحام (Port Congestion)\n"
            + "\n".join(alerts)
            + f"\n🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA"
        )
