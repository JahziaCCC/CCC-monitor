import os, json, math, threading, datetime, requests, websocket
from collections import defaultdict

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
API_KEY = os.environ["AISSTREAM_API_KEY"]

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
now = datetime.datetime.now(KSA_TZ)

CAPTURE_SECONDS = 600
GLOBAL_TEST_SECONDS = 20
TYPE_CACHE_FILE = "ais_type_cache.json"

WAITING_SPEED_KTS = 0.7
CONGESTION_RADIUS_KM = 250

SAUDI_BIG_BOX = [[10.0, 32.0], [32.5, 58.5]]

# KSA-only (tight)
KSA_RED_SEA = [[16.0, 34.0], [29.8, 41.8]]
KSA_GULF    = [[24.0, 48.4], [28.9, 52.6]]

# Regional corridors (wider)
REG_RED_SEA = [[12.0, 32.0], [30.5, 44.8]]
REG_GULF    = [[21.0, 47.0], [30.5, 56.5]]

# KSA ports
PORTS_KSA = {
    "ميناء جدة الإسلامي": {"lat": 21.484, "lon": 39.173},
    "ميناء الملك عبدالله (KAEC)": {"lat": 22.523, "lon": 39.089},
    "ميناء ينبع التجاري": {"lat": 24.0665, "lon": 38.0675},
    "ميناء جازان": {"lat": 16.9189, "lon": 42.5573},
    "ميناء ضباء": {"lat": 27.5606, "lon": 35.5440},
    "ميناء الملك عبدالعزيز (الدمام)": {"lat": 26.4410, "lon": 50.1485},
    "ميناء الجبيل التجاري": {"lat": 27.0241, "lon": 49.6793},
    "محطة نفط رأس تنورة": {"lat": 26.6726, "lon": 50.1219},
    "محطة نفط الجعيمة (Juaymah)": {"lat": 26.93, "lon": 50.06},
    "محطة نفط تناجيب (Tanajib)": {"lat": 27.7948, "lon": 48.8921},
}

# Regional ports (fallback)
PORTS_REGIONAL = {
    "ميناء راشد (دبي)": {"lat": 25.270, "lon": 55.275},
    "ميناء جبل علي (دبي)": {"lat": 24.985, "lon": 55.060},
    "ميناء خورفكان": {"lat": 25.340, "lon": 56.360},
    "ميناء الفجيرة": {"lat": 25.120, "lon": 56.330},
    "ميناء أبوظبي (خليفة)": {"lat": 24.810, "lon": 54.610},
    "ميناء حمد (قطر)": {"lat": 25.070, "lon": 51.610},
    "ميناء سلمان (البحرين)": {"lat": 26.150, "lon": 50.620},
    "ميناء الشويخ (الكويت)": {"lat": 29.360, "lon": 47.950},
    "ميناء صحار": {"lat": 24.490, "lon": 56.620},
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

def in_box(lat, lon, box):
    (a1, o1), (a2, o2) = box
    return (min(a1,a2) <= lat <= max(a1,a2)) and (min(o1,o2) <= lon <= max(o1,o2))

def run_stream(boxes, seconds, type_cache):
    opened = False
    subsent = False
    last_error = None

    samples_total = 0
    samples_pos = 0
    samples_static = 0

    vessels = {}
    points = []
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

        if len(points) < 10:
            points.append((lat, lon))

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
        "vessels": vessels, "latlon_window": win, "sample_points": points
    }

def compute_port_stats(vessels, ports, topn=7):
    # For each vessel: assign nearest port (even if far), and count those within radius
    stats = {k: {"within": 0, "waiting": 0, "tankers_conf": 0, "type_unknown": 0, "min_d": None} for k in ports.keys()}

    for _, v in vessels.items():
        best_name = None
        best_d = 10**9
        for name, p in ports.items():
            d = haversine_km(p["lat"], p["lon"], v["lat"], v["lon"])
            if d < best_d:
                best_d = d
                best_name = name

        if best_name is None:
            continue

        # track min distance always
        cur = stats[best_name]["min_d"]
        stats[best_name]["min_d"] = best_d if (cur is None or best_d < cur) else cur

        if best_d <= CONGESTION_RADIUS_KM:
            stats[best_name]["within"] += 1
            if v["waiting"]:
                stats[best_name]["waiting"] += 1

            t = v.get("type", 0)
            if t == 0:
                stats[best_name]["type_unknown"] += 1
            elif is_oil_tanker(t):
                stats[best_name]["tankers_conf"] += 1

    # Only show ports that have any signal: within>0 OR min_d not None
    usable = [(name, s) for name, s in stats.items() if s["min_d"] is not None]
    ranked = sorted(usable, key=lambda x: (x[1]["within"], x[1]["waiting"]), reverse=True)[:topn]
    return ranked

def hotspots(vessels, cell_deg=0.5, topn=5):
    grid = defaultdict(int)
    for _, v in vessels.items():
        lat = round(v["lat"]/cell_deg)*cell_deg
        lon = round(v["lon"]/cell_deg)*cell_deg
        grid[(lat, lon)] += 1
    ranked = sorted(grid.items(), key=lambda x: x[1], reverse=True)[:topn]
    return ranked

if __name__ == "__main__":
    type_cache = load_json(TYPE_CACHE_FILE, {})

    regional = run_stream([SAUDI_BIG_BOX], CAPTURE_SECONDS, type_cache)
    glob = run_stream([[[-90.0, -180.0], [90.0, 180.0]]], GLOBAL_TEST_SECONDS, type_cache)

    save_json(TYPE_CACHE_FILE, type_cache)

    all_v = regional["vessels"]

    ksa_v = {m:v for m,v in all_v.items() if (in_box(v["lat"], v["lon"], KSA_RED_SEA) or in_box(v["lat"], v["lon"], KSA_GULF))}
    reg_v = {m:v for m,v in all_v.items() if (in_box(v["lat"], v["lon"], REG_RED_SEA) or in_box(v["lat"], v["lon"], REG_GULF))}

    used_label = "KSA-only"
    used_v = ksa_v
    used_ports = PORTS_KSA

    note = ""
    if len(ksa_v) == 0:
        used_label = "Regional (no KSA coastal coverage)"
        used_v = reg_v
        used_ports = PORTS_REGIONAL
        note = "⚠️ لا توجد تغطية AIS قرب سواحل المملكة في هذه النافذة — تم التحويل تلقائيًا لعرض موانئ إقليمية + نقاط كثافة."

    port_rank = compute_port_stats(used_v, used_ports, topn=7)
    hot = hotspots(used_v, cell_deg=0.5, topn=7)

    pts = regional["sample_points"]
    pts_txt = "\n".join([f"• {i+1}) lat={p[0]:.4f}, lon={p[1]:.4f}" for i, p in enumerate(pts)]) if pts else "• لا يوجد"

    ports_lines = []
    for name, s in port_rank:
        within = s["within"]
        waiting = s["waiting"]
        tank_conf = s["tankers_conf"]
        unk = s["type_unknown"]
        mind = s["min_d"] if s["min_d"] is not None else 10**9

        # Only show meaningful lines (within>0 OR mind within 400km)
        if within == 0 and mind > 400:
            continue

        ports_lines.append(
            f"• {name}: ضمن {CONGESTION_RADIUS_KM}كم = {within} | منتظرة/راسية {waiting} | ناقلات مؤكدة {tank_conf} | نوع غير معروف {unk} | أقرب مسافة ~{mind:.0f}كم"
        )

    hot_lines = []
    for (lat, lon), cnt in hot:
        hot_lines.append(f"• خلية lat={lat:.1f}, lon={lon:.1f} : {cnt} سفينة")

    msg = f"""🚢 تقرير الملاحة (موانئ + محطات نفط) — Smart Clean
🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA

════════════════════
📡 Saudi Big Box:
• messages: {regional['messages']} | position: {regional['position']} | static: {regional['static']}
• vessels unique (all): {len(all_v)}
• lat/lon window (all): {regional['latlon_window'] or 'N/A'}

🇸🇦 KSA-only vessels: {len(ksa_v)}
🌐 Regional vessels: {len(reg_v)}
📍 الحساب المستخدم: {used_label}
{note}

════════════════════
⚓ أقرب الموانئ/المحطات (منطق نظيف):
""" + ("\n".join(ports_lines) if ports_lines else "• لا يوجد ضمن نطاقات مفيدة") + f"""

════════════════════
🔥 نقاط كثافة (Hotspots):
""" + ("\n".join(hot_lines) if hot_lines else "• لا يوجد") + f"""

════════════════════
🌍 اختبار عالمي ({GLOBAL_TEST_SECONDS}s):
• global_messages: {glob['messages']} | global_position: {glob['position']}

════════════════════
📌 عينة نقاط (أول 10 من الدفق العام):
{pts_txt}
"""

    send_telegram(msg)
