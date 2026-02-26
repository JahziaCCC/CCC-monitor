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

# =========================
# KSA-only (tight)
# =========================
KSA_RED_SEA = [[16.0, 34.0], [29.8, 41.8]]
KSA_GULF    = [[24.0, 48.4], [28.9, 52.6]]

# =========================
# Regional corridors (wider)
# =========================
REG_RED_SEA = [[12.0, 32.0], [30.5, 44.8]]
REG_GULF    = [[21.0, 47.0], [30.5, 56.5]]

# =========================
# KSA Ports + Oil Terminals
# =========================
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

# =========================
# Regional Ports (fallback when KSA coverage=0)
# (إحداثيات تقريبية كافية للتصنيف التشغيلي)
# =========================
PORTS_REGIONAL = {
    # UAE
    "ميناء جبل علي (دبي)": {"lat": 24.985, "lon": 55.060},
    "ميناء راشد (دبي)": {"lat": 25.270, "lon": 55.275},
    "ميناء خورفكان": {"lat": 25.340, "lon": 56.360},
    "ميناء الفجيرة": {"lat": 25.120, "lon": 56.330},
    "ميناء أبوظبي (خليفة)": {"lat": 24.810, "lon": 54.610},
    # Qatar / Bahrain / Kuwait
    "ميناء حمد (قطر)": {"lat": 25.070, "lon": 51.610},
    "ميناء سلمان (البحرين)": {"lat": 26.150, "lon": 50.620},
    "ميناء الشويخ (الكويت)": {"lat": 29.360, "lon": 47.950},
    # Oman (north)
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

def compute_nearest_ports(vessels, ports, topn=5):
    # returns list of (port_name, count_within_R, waiting, tankers, min_dist)
    stats = {k: {"total": 0, "waiting": 0, "tankers": 0, "min_d": 10**9} for k in ports.keys()}

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

        # track min distance even if outside radius
        stats[best_name]["min_d"] = min(stats[best_name]["min_d"], best_d)

        if best_d <= CONGESTION_RADIUS_KM:
            stats[best_name]["total"] += 1
            if v["waiting"]:
                stats[best_name]["waiting"] += 1
            if is_oil_tanker(v.get("type", 0)):
                stats[best_name]["tankers"] += 1

    ranked = sorted(stats.items(), key=lambda x: (x[1]["total"], x[1]["waiting"]), reverse=True)
    out = []
    for name, s in ranked[:topn]:
        out.append((name, s["total"], s["waiting"], s["tankers"], s["min_d"]))
    return out

def hotspots(vessels, cell_deg=0.5, topn=5):
    # grid by rounding to 0.5deg
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
    ports_used = PORTS_KSA

    coverage_note = ""
    if len(ksa_v) == 0:
        used_label = "Regional (no KSA coastal coverage)"
        used_v = reg_v
        ports_used = PORTS_REGIONAL
        coverage_note = "⚠️ لا توجد تغطية AIS قرب سواحل المملكة في هذه النافذة — تم عرض أقرب الموانئ الإقليمية + نقاط الكثافة بدل أصفار موانئ السعودية."

    # nearest ports summary
    near_ports = compute_nearest_ports(used_v, ports_used, topn=7)

    # hotspots summary
    hot = hotspots(used_v, cell_deg=0.5, topn=7)

    # sample points (global stream sample)
    pts = regional["sample_points"]
    pts_txt = "\n".join([f"• {i+1}) lat={p[0]:.4f}, lon={p[1]:.4f}" for i, p in enumerate(pts)]) if pts else "• لا يوجد"

    ports_lines = []
    for name, total, waiting, tankers, mind in near_ports:
        ports_lines.append(f"• {name}: ضمن {CONGESTION_RADIUS_KM}كم = {total} | منتظرة/راسية {waiting} | ناقلات {tankers} | أقرب مسافة ~{mind:.0f}كم")

    hot_lines = []
    for (lat, lon), cnt in hot:
        hot_lines.append(f"• خلية lat={lat:.1f}, lon={lon:.1f} : {cnt} سفينة")

    msg = f"""🚢 تقرير الملاحة (موانئ + محطات نفط) — KSA/Regional Smart
🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA

════════════════════
📡 Saudi Big Box:
• messages: {regional['messages']} | position: {regional['position']} | static: {regional['static']}
• vessels unique (all): {len(all_v)}
• lat/lon window (all): {regional['latlon_window'] or 'N/A'}

🇸🇦 KSA-only vessels: {len(ksa_v)}
🌐 Regional vessels: {len(reg_v)}
📍 الحساب المستخدم: {used_label}
{coverage_note}

════════════════════
⚓ أقرب الموانئ/المحطات (حسب المجموعة المستخدمة):
""" + ("\n".join(ports_lines) if ports_lines else "• لا يوجد") + f"""

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
