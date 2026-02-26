import os
import json
import threading
import datetime
import requests
import websocket

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
API_KEY = os.environ["AISSTREAM_API_KEY"]

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
now = datetime.datetime.now(KSA_TZ)

CAPTURE_SECONDS = 180

# صندوق كبير يغطي البحر الأحمر + الخليج + سواحل المملكة
SAUDI_REGION_BOX = [[10.0, 32.0], [32.5, 58.5]]

STATE_FILE = "ais_ports_state.json"
TYPE_CACHE_FILE = "ais_type_cache.json"

WAITING_SPEED_KTS = 0.7
ALERT_WAITING_SPIKE = 8

# =========================
# Port Zones (wide boxes)
# format: [[minLat, minLon], [maxLat, maxLon]]
# =========================
PORT_ZONES = {
    # Red Sea ports
    "ميناء جدة الإسلامي": [[20.6, 38.3], [22.3, 40.2]],
    "ميناء الملك عبدالله (KAEC)": [[21.8, 38.3], [23.1, 40.0]],
    "ميناء ينبع التجاري": [[23.4, 37.1], [25.0, 38.9]],
    "ميناء جازان": [[16.2, 41.7], [17.6, 43.3]],
    "ميناء ضباء": [[26.9, 34.7], [28.2, 36.4]],

    # Gulf ports
    "ميناء الملك عبدالعزيز (الدمام)": [[25.7, 49.3], [27.3, 51.2]],
    "ميناء الجبيل التجاري": [[26.6, 48.8], [27.7, 50.6]],

    # Oil terminals (wide offshore areas)
    "محطة نفط رأس تنورة": [[26.2, 49.5], [27.2, 50.9]],
    "محطة نفط الجعيمة (Juaymah)": [[26.4, 49.3], [27.4, 50.8]],
    "محطة نفط تناجيب (Tanajib)": [[27.3, 48.2], [28.4, 49.8]],
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

def normalize_box(box):
    (lat1, lon1), (lat2, lon2) = box
    return min(lat1, lat2), max(lat1, lat2), min(lon1, lon2), max(lon1, lon2)

def in_box(lat, lon, box):
    min_lat, max_lat, min_lon, max_lon = normalize_box(box)
    return (min_lat <= lat <= max_lat) and (min_lon <= lon <= max_lon)

def in_any_zone(lat, lon):
    for name, box in PORT_ZONES.items():
        if in_box(lat, lon, box):
            return name
    return None

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

    # 2) fallback to metadata (important)
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
    if waiting >= 15 or total >= 60:
        return "🔴 شديد"
    if waiting >= 7 or total >= 30:
        return "🟠 مرتفع"
    if waiting >= 3 or total >= 12:
        return "🟡 متوسط"
    return "🟢 منخفض"

def run_capture():
    type_cache = load_json(TYPE_CACHE_FILE, {})  # mmsi -> type

    # per-zone stats
    stats = {name: {"total": 0, "waiting": 0, "tankers": 0} for name in PORT_ZONES.keys()}

    # track unique MMSI per zone to avoid double count
    seen_in_zone = {name: set() for name in PORT_ZONES.keys()}

    samples_total = 0
    samples_pos = 0
    samples_static = 0
    valid_latlon = 0
    near_hits = 0

    def on_open(ws):
        ws.send(json.dumps({
            "APIKey": API_KEY,
            "BoundingBoxes": [SAUDI_REGION_BOX]
        }))

    def on_message(ws, message):
        nonlocal samples_total, samples_pos, samples_static, valid_latlon, near_hits
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

        zone = in_any_zone(lat, lon)
        if not zone:
            return

        near_hits += 1

        # avoid double count for same vessel in same zone
        if mmsi in seen_in_zone[zone]:
            return
        seen_in_zone[zone].add(mmsi)

        vtype = 0
        if isinstance(blk, dict) and "Type" in blk:
            try:
                vtype = int(blk.get("Type", 0))
            except Exception:
                vtype = 0
        if not vtype:
            vtype = type_cache.get(mmsi, 0)

        stats[zone]["total"] += 1
        if is_waiting(blk) if isinstance(blk, dict) else False:
            stats[zone]["waiting"] += 1
        if is_oil_tanker(vtype):
            stats[zone]["tankers"] += 1

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

    return samples_total, samples_pos, samples_static, valid_latlon, near_hits, stats

if __name__ == "__main__":
    prev_state = load_json(STATE_FILE, {"ports": {}, "ts": ""})

    total, pos, stat, valid_latlon, near_hits, stats = run_capture()

    # rank by waiting then total
    ranked = sorted(stats.items(), key=lambda x: (x[1]["waiting"], x[1]["total"]), reverse=True)

    lines = []
    alerts = []

    for name, v in ranked:
        prev = (prev_state.get("ports", {}).get(name) or {})
        d_wait = v["waiting"] - int(prev.get("waiting", 0))
        d_total = v["total"] - int(prev.get("total", 0))

        lvl = congestion_level(v["total"], v["waiting"])
        lines.append(
            f"{lvl} {name}\n"
            f"• إجمالي: {v['total']} (Δ {d_total:+}) | منتظرة/راسية: {v['waiting']} (Δ {d_wait:+}) | ناقلات: {v['tankers']}"
        )

        if d_wait >= ALERT_WAITING_SPIKE and v["waiting"] >= 5:
            alerts.append(f"🚨 ازدحام متصاعد في {name}: +{d_wait} سفن منتظرة")

    save_json(STATE_FILE, {"ports": stats, "ts": now.strftime("%Y-%m-%d %H:%M")})

    header = f"""⚓ تقرير ازدحام موانئ المملكة + محطات النفط (Zones)
🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA

════════════════════
📡 رسائل: {total}
📍 Position: {pos} | Static: {stat}

🔎 تشخيص:
• Valid lat/lon: {valid_latlon}
• Near ports hits: {near_hits}

════════════════════
"""
    body = "\n\n".join(lines) if lines else "لا توجد بيانات قرب الموانئ/المحطات ضمن نافذة الالتقاط."
    send_telegram(header + body)

    if alerts:
        send_telegram(
            "🚨 تنبيهات ازدحام (Port Congestion)\n"
            + "\n".join(alerts)
            + f"\n🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA"
        )
