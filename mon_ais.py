import os, json, math, threading, datetime, time, requests, websocket

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
API_KEY = os.environ["AISSTREAM_API_KEY"]

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
now = datetime.datetime.now(KSA_TZ)

CAPTURE_SECONDS = 600          # 10 دقائق
GLOBAL_TEST_SECONDS = 20
TYPE_CACHE_FILE = "ais_type_cache.json"

WAITING_SPEED_KTS = 0.7
CONGESTION_RADIUS_KM = 200

# =========================
# ✅ ممران ساحليان فقط (KSA corridors)
# =========================
# البحر الأحمر بمحاذاة سواحل المملكة (يغطي جدة/ينبع/ضباء ويستبعد الأردن/الإمارات)
RED_SEA_BOX = [[14.0, 32.0], [30.5, 42.5]]   # lat 14..30.5, lon 32..42.5

# الخليج العربي بمحاذاة سواحل المملكة (يغطي الدمام/الجبيل/رأس تنورة ويستبعد خليج عمان)
ARABIAN_GULF_BOX = [[23.0, 47.0], [29.7, 52.7]]  # lat 23..29.7, lon 47..52.7

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

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1 = math.radians(lat1); p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1); dlon = math.radians(lon2 - lon1)
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

def extract_lat_lon(data):
    # robust keys
    meta = data.get("MetaData") or data.get("Metadata") or {}
    lat = None; lon = None

    for lk in ("latitude","Latitude","lat","LAT"):
        if lk in meta:
            try: lat = float(meta[lk]); break
            except: pass
    for ok in ("longitude","Longitude","lon","LON","lng","Lng"):
        if ok in meta:
            try: lon = float(meta[ok]); break
            except: pass

    if lat is None or lon is None:
        msg = data.get("Message", {})
        for _, blk in msg.items():
            if isinstance(blk, dict) and "Latitude" in blk and "Longitude" in blk:
                try:
                    lat = float(blk["Latitude"]); lon = float(blk["Longitude"])
                    break
                except:
                    pass

    if lat is None or lon is None:
        raise KeyError

    # sanity + swap if needed
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        if (-90 <= lon <= 90 and -180 <= lat <= 180):
            lat, lon = lon, lat
        else:
            raise KeyError

    return lat, lon

def get_nav_status(data):
    msg = data.get("Message", {})
    for _, blk in msg.items():
        if isinstance(blk, dict):
            for k in ("NavigationalStatus","NavStatus","NavigationStatus"):
                if k in blk:
                    try: return int(blk[k])
                    except: pass
    return None

def get_sog_knots(data):
    msg = data.get("Message", {})
    for _, blk in msg.items():
        if isinstance(blk, dict):
            for k in ("Sog","SOG","SpeedOverGround","Speed"):
                if k in blk:
                    try: return float(blk[k])
                    except: pass
    return None

def is_waiting(data):
    nav = get_nav_status(data)
    if nav in (1,5):
        return True
    sog = get_sog_knots(data)
    if sog is not None and sog <= WAITING_SPEED_KTS:
        return True
    return False

def is_oil_tanker(vtype):
    try: v = int(vtype)
    except: v = 0
    return 80 <= v <= 89

def congestion_level(total, waiting):
    if waiting >= 20 or total >= 80: return "🔴 شديد"
    if waiting >= 10 or total >= 40: return "🟠 مرتفع"
    if waiting >= 4  or total >= 15: return "🟡 متوسط"
    return "🟢 منخفض"

def run_stream(boxes, seconds, type_cache):
    opened = False
    subsent = False
    last_error = None

    samples_total = 0
    samples_pos = 0
    samples_static = 0

    vessels = {}  # mmsi -> {lat,lon,waiting,type}

    min_lat = 999; max_lat = -999; min_lon = 999; max_lon = -999

    def on_open(ws):
        nonlocal opened, subsent
        opened = True
        ws.send(json.dumps({"APIKey": API_KEY, "BoundingBoxes": boxes}))
        subsent = True

    def on_error(ws, err):
        nonlocal last_error
        last_error = str(err)

    def on_message(ws, message):
        nonlocal samples_total, samples_pos, samples_static
        nonlocal min_lat, max_lat, min_lon, max_lon

        samples_total += 1
        try:
            data = json.loads(message)
        except:
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
            except:
                pass
            return

        try:
            lat, lon = extract_lat_lon(data)
        except:
            return

        samples_pos += 1
        min_lat = min(min_lat, lat); max_lat = max(max_lat, lat)
        min_lon = min(min_lon, lon); max_lon = max(max_lon, lon)

        vessels[mmsi] = {
            "lat": lat,
            "lon": lon,
            "waiting": is_waiting(data),
            "type": type_cache.get(mmsi, 0)
        }

    ws = websocket.WebSocketApp(
        "wss://stream.aisstream.io/v0/stream",
        on_open=on_open, on_message=on_message, on_error=on_error
    )

    timer = threading.Timer(seconds, lambda: ws.close())
    timer.start()
    ws.run_forever(ping_interval=20, ping_timeout=10)
    timer.cancel()

    win = None
    if samples_pos > 0:
        win = f"lat[{min_lat:.4f},{max_lat:.4f}] lon[{min_lon:.4f},{max_lon:.4f}]"

    return {
        "opened": opened, "subsent": subsent, "last_error": last_error,
        "messages": samples_total, "position": samples_pos, "static": samples_static,
        "vessels": vessels, "latlon_window": win
    }

def compute_ports(vessels):
    ports_now = {k: {"total": 0, "waiting": 0, "tankers": 0} for k in PORTS.keys()}
    near50 = 0
    nearR = 0
    b0_50 = 0; b50_R = 0; bRp = 0

    for _, v in vessels.items():
        best = 10**9
        for name, p in PORTS.items():
            d = haversine_km(p["lat"], p["lon"], v["lat"], v["lon"])
            best = min(best, d)
            if d <= CONGESTION_RADIUS_KM:
                ports_now[name]["total"] += 1
                if v["waiting"]:
                    ports_now[name]["waiting"] += 1
                if is_oil_tanker(v.get("type", 0)):
                    ports_now[name]["tankers"] += 1

        if best <= 50:
            near50 += 1; b0_50 += 1
        elif best <= CONGESTION_RADIUS_KM:
            nearR += 1; b50_R += 1
        else:
            bRp += 1

    return ports_now, near50, (near50 + nearR), (b0_50, b50_R, bRp)

if __name__ == "__main__":
    type_cache = load_json(TYPE_CACHE_FILE, {})

    # ✅ اتصال واحد + صندوقين فقط
    regional = run_stream([RED_SEA_BOX, ARABIAN_GULF_BOX], CAPTURE_SECONDS, type_cache)

    # global test (للتأكد الخدمة شغالة)
    glob = run_stream([[[-90.0, -180.0], [90.0, 180.0]]], GLOBAL_TEST_SECONDS, type_cache)

    save_json(TYPE_CACHE_FILE, type_cache)

    vessels = regional["vessels"]
    ports_now, near50, nearR, buckets = compute_ports(vessels)

    # counts by corridor (تقريبًا عبر lat/lon window يكفي تشخيص، بس نضيف عد تقريبي)
    red_count = 0
    gulf_count = 0
    for _, v in vessels.items():
        lat = v["lat"]; lon = v["lon"]
        if (RED_SEA_BOX[0][0] <= lat <= RED_SEA_BOX[1][0]) and (RED_SEA_BOX[0][1] <= lon <= RED_SEA_BOX[1][1]):
            red_count += 1
        if (ARABIAN_GULF_BOX[0][0] <= lat <= ARABIAN_GULF_BOX[1][0]) and (ARABIAN_GULF_BOX[0][1] <= lon <= ARABIAN_GULF_BOX[1][1]):
            gulf_count += 1

    ranked = sorted(ports_now.items(), key=lambda x: (x[1]["waiting"], x[1]["total"]), reverse=True)

    lines = []
    for name, v in ranked:
        lvl = congestion_level(v["total"], v["waiting"])
        lines.append(
            f"{lvl} {name}\n"
            f"• ضمن {CONGESTION_RADIUS_KM}كم: إجمالي {v['total']} | منتظرة/راسية {v['waiting']} | ناقلات {v['tankers']}"
        )

    msg = f"""⚓ تقرير ازدحام موانئ المملكة + محطات النفط (KSA Coastal Corridors)
🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA

════════════════════
📡 إقليمي (Red Sea + Gulf):
• messages: {regional['messages']} | position: {regional['position']} | static: {regional['static']}
• vessels unique: {len(vessels)}
• corridor counts (approx): RedSea={red_count}, Gulf={gulf_count}

📍 قرب موانئ/محطات المملكة:
• <=50كم={near50} | <= {CONGESTION_RADIUS_KM}كم={nearR}
• nearest dist buckets: 0-50={buckets[0]}, 50-{CONGESTION_RADIUS_KM}={buckets[1]}, >{CONGESTION_RADIUS_KM}={buckets[2]}
• lat/lon window: {regional['latlon_window'] or 'N/A'}

🌍 اختبار عالمي ({GLOBAL_TEST_SECONDS}s):
• global_messages: {glob['messages']} | global_position: {glob['position']}

🔎 تشخيص:
• opened: {regional['opened']} | subscription_sent: {regional['subsent']}
• last_error: {regional['last_error'] or 'N/A'}

════════════════════
""" + "\n\n".join(lines)

    send_telegram(msg)
