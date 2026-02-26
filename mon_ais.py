import os, json, math, threading, datetime, time, requests, websocket

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
API_KEY = os.environ["AISSTREAM_API_KEY"]

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
now = datetime.datetime.now(KSA_TZ)

# اجعلها أطول شوي لرفع فرصة التقاط قرب الموانئ
CAPTURE_SECONDS = 600   # 10 دقائق
GLOBAL_TEST_SECONDS = 20
RETRIES = 2
RETRY_SLEEP = 20

TYPE_CACHE_FILE = "ais_type_cache.json"

WAITING_SPEED_KTS = 0.7
CONGESTION_RADIUS_KM = 200  # نطاق واسع يشمل مناطق الانتظار offshore

SAUDI_REGION_BOX = [[10.0, 32.0], [32.5, 58.5]]  # [[lat,lon],[lat,lon]]

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
    if nav in (1,5):  # anchored/moored
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
    samples_total = 0
    samples_pos = 0
    samples_static = 0

    opened = False
    subsent = False
    last_error = None

    vessels = {}  # mmsi -> {lat,lon,waiting,type}

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

        vtype = type_cache.get(mmsi, 0)
        vessels[mmsi] = {
            "lat": lat,
            "lon": lon,
            "waiting": is_waiting(data),
            "type": vtype
        }

    ws = websocket.WebSocketApp(
        "wss://stream.aisstream.io/v0/stream",
        on_open=on_open,
        on_message=on_message,
        on_error=on_error
    )

    timer = threading.Timer(seconds, lambda: ws.close())
    timer.start()
    ws.run_forever(ping_interval=20, ping_timeout=10)
    timer.cancel()

    return {
        "opened": opened,
        "subsent": subsent,
        "last_error": last_error,
        "messages": samples_total,
        "position": samples_pos,
        "static": samples_static,
        "vessels": vessels
    }

def compute_ports(vessels):
    ports_now = {k: {"total": 0, "waiting": 0, "tankers": 0} for k in PORTS.keys()}
    near50 = 0
    near200 = 0

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
            near50 += 1
        if best <= CONGESTION_RADIUS_KM:
            near200 += 1

    return ports_now, near50, near200

if __name__ == "__main__":
    type_cache = load_json(TYPE_CACHE_FILE, {})

    regional = None
    for i in range(RETRIES):
        regional = run_stream([SAUDI_REGION_BOX], CAPTURE_SECONDS, type_cache)
        if regional["messages"] > 0:
            break
        time.sleep(RETRY_SLEEP)

    # global test (always) to distinguish "service ok" vs "regional stream empty"
    global_box = [[-90.0, -180.0], [90.0, 180.0]]
    glob = run_stream([global_box], GLOBAL_TEST_SECONDS, type_cache)

    save_json(TYPE_CACHE_FILE, type_cache)

    vessels = regional["vessels"]
    ports_now, near50, near200 = compute_ports(vessels)

    ranked = sorted(ports_now.items(), key=lambda x: (x[1]["waiting"], x[1]["total"]), reverse=True)

    lines = []
    for name, v in ranked:
        lvl = congestion_level(v["total"], v["waiting"])
        lines.append(
            f"{lvl} {name}\n"
            f"• ضمن {CONGESTION_RADIUS_KM}كم: إجمالي {v['total']} | منتظرة/راسية {v['waiting']} | ناقلات {v['tankers']}"
        )

    note = ""
    if regional["messages"] == 0 and glob["messages"] > 0:
        note = "⚠️ ملاحظة: AISStream شغّال عالميًا لكن لم يرسل دفقًا داخل نطاق السعودية في هذه النافذة (احتمال Throttle/تغطية لحظية)."

    msg = f"""⚓ تقرير ازدحام موانئ المملكة + محطات النفط (Stable Regional)
🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA

════════════════════
📡 إقليمي (السعودية):
• messages: {regional['messages']} | position: {regional['position']} | static: {regional['static']}
• vessels unique: {len(vessels)}
• قرب الموانئ: <=50كم={near50} | <= {CONGESTION_RADIUS_KM}كم={near200}

🌍 اختبار عالمي ({GLOBAL_TEST_SECONDS}s):
• global_messages: {glob['messages']} | global_position: {glob['position']}

🔎 تشخيص:
• opened: {regional['opened']} | subscription_sent: {regional['subsent']}
• last_error: {regional['last_error'] or 'N/A'}

{note}
════════════════════
""" + "\n\n".join(lines)

    send_telegram(msg)
