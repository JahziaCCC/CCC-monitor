import os, json, math, threading, datetime, requests, websocket

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
API_KEY = os.environ["AISSTREAM_API_KEY"]

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
now = datetime.datetime.now(KSA_TZ)

CAPTURE_SECONDS = 600
GLOBAL_TEST_SECONDS = 20

TYPE_CACHE_FILE = "ais_type_cache.json"

WAITING_SPEED_KTS = 0.7
CONGESTION_RADIUS_KM = 250  # 250كم مناسب للموانئ/محطات النفط + مناطق الانتظار القريبة

# ✅ اشتراك ثابت (واسع) لأنه يشتغل عندك
SAUDI_BIG_BOX = [[10.0, 32.0], [32.5, 58.5]]

# ✅ فلترة محلية ضيّقة لسواحل المملكة فقط
# البحر الأحمر (ساحل المملكة) — يستبعد شمالاً جهة فلسطين/إسرائيل
KSA_RED_SEA = [[16.0, 34.0], [29.8, 41.8]]   # lat 16..29.8, lon 34..41.8

# الخليج العربي (ساحل المملكة) — يستبعد دبي/عُمان
KSA_GULF = [[24.0, 48.4], [28.9, 52.6]]      # lat 24..28.9, lon 48.4..52.6

PORTS = {
    # Red Sea (KSA)
    "ميناء جدة الإسلامي": {"lat": 21.484, "lon": 39.173},
    "ميناء الملك عبدالله (KAEC)": {"lat": 22.523, "lon": 39.089},
    "ميناء ينبع التجاري": {"lat": 24.0665, "lon": 38.0675},
    "ميناء جازان": {"lat": 16.9189, "lon": 42.5573},  # جازان قريب من الحد، ممكن يطلع قليل حسب التغطية
    "ميناء ضباء": {"lat": 27.5606, "lon": 35.5440},

    # Gulf (KSA)
    "ميناء الملك عبدالعزيز (الدمام)": {"lat": 26.4410, "lon": 50.1485},
    "ميناء الجبيل التجاري": {"lat": 27.0241, "lon": 49.6793},

    # Oil terminals (KSA)
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

    regional = run_stream([SAUDI_BIG_BOX], CAPTURE_SECONDS, type_cache)
    glob = run_stream([[[-90.0, -180.0], [90.0, 180.0]]], GLOBAL_TEST_SECONDS, type_cache)

    save_json(TYPE_CACHE_FILE, type_cache)

    all_v = regional["vessels"]

    # ✅ فلترة KSA-only: لازم تكون السفينة داخل أحد الممرين (البحر الأحمر KSA أو الخليج KSA)
    ksa_v = {}
    for m, v in all_v.items():
        if in_box(v["lat"], v["lon"], KSA_RED_SEA) or in_box(v["lat"], v["lon"], KSA_GULF):
            ksa_v[m] = v

    excluded = len(all_v) - len(ksa_v)

    ports_now, near50, nearR, buckets = compute_ports(ksa_v)
    ranked = sorted(ports_now.items(), key=lambda x: (x[1]["waiting"], x[1]["total"]), reverse=True)

    lines = []
    for name, v in ranked:
        lvl = congestion_level(v["total"], v["waiting"])
        lines.append(
            f"{lvl} {name}\n"
            f"• ضمن {CONGESTION_RADIUS_KM}كم: إجمالي {v['total']} | منتظرة/راسية {v['waiting']} | ناقلات {v['tankers']}"
        )

    pts = regional["sample_points"]
    pts_txt = "\n".join([f"• {i+1}) lat={p[0]:.4f}, lon={p[1]:.4f}" for i, p in enumerate(pts)]) if pts else "• لا يوجد"

    msg = f"""⚓ تقرير ازدحام موانئ المملكة + محطات النفط (KSA-only Filter)
🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA

════════════════════
📡 إقليمي (Saudi Big Box):
• messages: {regional['messages']} | position: {regional['position']} | static: {regional['static']}
• vessels unique (all): {len(all_v)}
• lat/lon window (all): {regional['latlon_window'] or 'N/A'}

🇸🇦 فلترة “سواحل المملكة فقط”:
• KSA coastal vessels: {len(ksa_v)}
• Excluded (outside KSA coastal corridors): {excluded}

📍 قرب موانئ/محطات المملكة (من السفن السعودية فقط):
• <=50كم={near50} | <= {CONGESTION_RADIUS_KM}كم={nearR}
• nearest dist buckets: 0-50={buckets[0]}, 50-{CONGESTION_RADIUS_KM}={buckets[1]}, >{CONGESTION_RADIUS_KM}={buckets[2]}

🌍 اختبار عالمي ({GLOBAL_TEST_SECONDS}s):
• global_messages: {glob['messages']} | global_position: {glob['position']}

🔎 تشخيص:
• opened: {regional['opened']} | subscription_sent: {regional['subsent']}
• last_error: {regional['last_error'] or 'N/A'}

════════════════════
📌 عينة نقاط (أول 10 من الدفق العام):
{pts_txt}

════════════════════
""" + "\n\n".join(lines)

    send_telegram(msg)
