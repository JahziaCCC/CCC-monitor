import os
import json
import math
import time
import threading
import datetime
import requests
import websocket

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
API_KEY = os.environ["AISSTREAM_API_KEY"]

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
now = datetime.datetime.now(KSA_TZ)

TYPE_CACHE_FILE = "ais_type_cache.json"

# ===== إعدادات المسح =====
CAPTURE_EACH_SECONDS = 45      # مدة الالتقاط لكل ميناء/محطة
SLEEP_BETWEEN = 2              # راحة بسيطة بين الاتصالات
BOX_RADIUS_KM = 120            # صندوق حول الميناء/المحطة (يغطي مناطق الانتظار offshore)

WAITING_SPEED_KTS = 0.7        # (احتياطي) لو توفرت السرعة
# ملاحظة: nav status غالبًا ما يجي دائمًا مع AISStream، فبنستخدمه إذا توفر

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
    # 1 deg lon = 111km * cos(lat)
    c = math.cos(math.radians(lat))
    if c < 0.2:
        c = 0.2
    return km / (111.0 * c)

def make_box(lat, lon, radius_km):
    dlat = km_to_deg_lat(radius_km)
    dlon = km_to_deg_lon(radius_km, lat)
    return [[lat - dlat, lon - dlon], [lat + dlat, lon + dlon]]

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
    # الأفضل: MetaData (غالبًا موجود)
    meta = data.get("MetaData") or data.get("Metadata") or {}
    if "latitude" in meta and "longitude" in meta:
        return float(meta["latitude"]), float(meta["longitude"])
    # fallback: Message blocks
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

def capture_for_box(box, seconds, type_cache):
    seen = set()
    waiting = set()
    tankers = set()
    samples_total = 0
    samples_pos = 0
    samples_static = 0

    def on_open(ws):
        ws.send(json.dumps({"APIKey": API_KEY, "BoundingBoxes": [box]}))

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
            _ = extract_lat_lon(data)
        except Exception:
            return

        samples_pos += 1
        seen.add(mmsi)

        # waiting
        if is_waiting(data):
            waiting.add(mmsi)

        # tanker by cached/static type (إذا ما توفر الآن يتحسن مع الوقت)
        vtype = type_cache.get(mmsi, 0)
        if is_oil_tanker(vtype):
            tankers.add(mmsi)

    ws = websocket.WebSocketApp(
        "wss://stream.aisstream.io/v0/stream",
        on_open=on_open,
        on_message=on_message
    )

    timer = threading.Timer(seconds, lambda: ws.close())
    timer.start()
    ws.run_forever(ping_interval=20, ping_timeout=10)
    timer.cancel()

    return {
        "samples_total": samples_total,
        "samples_pos": samples_pos,
        "samples_static": samples_static,
        "ships": len(seen),
        "waiting": len(waiting),
        "tankers": len(tankers)
    }

def level(total, waiting):
    if waiting >= 15 or total >= 60:
        return "🔴 شديد"
    if waiting >= 7 or total >= 30:
        return "🟠 مرتفع"
    if waiting >= 3 or total >= 12:
        return "🟡 متوسط"
    return "🟢 منخفض"

if __name__ == "__main__":
    type_cache = load_json(TYPE_CACHE_FILE, {})

    lines = []
    any_hits = 0
    diag_msgs = 0
    diag_pos = 0
    diag_static = 0

    for name, p in SITES.items():
        box = make_box(p["lat"], p["lon"], BOX_RADIUS_KM)
        r = capture_for_box(box, CAPTURE_EACH_SECONDS, type_cache)

        diag_msgs += r["samples_total"]
        diag_pos += r["samples_pos"]
        diag_static += r["samples_static"]

        if r["ships"] > 0:
            any_hits += 1
            lvl = level(r["ships"], r["waiting"])
            lines.append(
                f"{lvl} {name}\n"
                f"• إجمالي ضمن ~{BOX_RADIUS_KM}كم: {r['ships']} | منتظرة/راسية: {r['waiting']} | ناقلات (Type cache): {r['tankers']}"
            )
        else:
            lines.append(
                f"⚠️ {name}\n"
                f"• لا توجد تغطية AIS قريبة ضمن نافذة الالتقاط ({CAPTURE_EACH_SECONDS}s)"
            )

        time.sleep(SLEEP_BETWEEN)

    save_json(TYPE_CACHE_FILE, type_cache)

    header = f"""⚓ تقرير ازدحام موانئ المملكة + محطات النفط (Port Sweep)
🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA

════════════════════
📡 تشخيص:
• sites scanned: {len(SITES)}
• sites with hits: {any_hits}
• total messages: {diag_msgs}
• total position: {diag_pos}
• total static: {diag_static}

📌 ملاحظة:
• AISStream تغطيتها تختلف حسب المحطات الأرضية ولا تضمن تغطية كاملة قرب كل ميناء/محطة في كل وقت. 
"""

    send_telegram(header + "\n════════════════════\n" + "\n\n".join(lines))
