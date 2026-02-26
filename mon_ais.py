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

CAPTURE_SECONDS = 180  # نافذة الالتقاط (ثواني)

# =========================
# Saudi Ports + Oil Terminals
# =========================
# radius_km: نصف قطر الرصد حول الموقع (للازدحام قرب الميناء/المحطة)
PORTS = {
    # =======================
    # موانئ البحر الأحمر
    # =======================
    "ميناء جدة الإسلامي": {"lat": 21.484, "lon": 39.173, "radius_km": 18},
    "ميناء الملك عبدالله (KAEC)": {"lat": 22.523, "lon": 39.089, "radius_km": 18},
    "ميناء ينبع التجاري": {"lat": 24.0665, "lon": 38.0675, "radius_km": 16},
    "ميناء جازان": {"lat": 16.9189, "lon": 42.5573, "radius_km": 16},
    "ميناء ضباء": {"lat": 27.5606, "lon": 35.5440, "radius_km": 14},

    # =======================
    # موانئ الخليج العربي
    # =======================
    "ميناء الملك عبدالعزيز (الدمام)": {"lat": 26.4410, "lon": 50.1485, "radius_km": 20},
    "ميناء الجبيل التجاري": {"lat": 27.0241, "lon": 49.6793, "radius_km": 20},

    # =======================
    # محطات النفط (Oil Terminals)
    # =======================
    # رأس تنورة (Port of Ras Tanura / حدود الميناء ضمن كتيب أرامكو)  [oai_citation:1‡Aramco](https://www.aramco.com/-/media/downloads/working-with-us/ports-and-terminals-july-2025/03--ras-tanura-port--si--np-compressed.pdf?utm_source=chatgpt.com)
    "محطة نفط رأس تنورة": {"lat": 26.6726, "lon": 50.1219, "radius_km": 24},  # نقطة تمثيلية قرب منطقة الميناء/التيرمنال

    # الجعيمة (Juaymah Terminal)  [oai_citation:2‡MagicPort](https://magicport.ai/ports/saudi-arabia/juaymah-terminal-port-sajut?utm_source=chatgpt.com)
    "محطة نفط الجعيمة (Juaymah)": {"lat": 26.93, "lon": 50.06, "radius_km": 26},

    # تناجيب (Tanajib Port)  [oai_citation:3‡vesselfinder.com](https://www.vesselfinder.com/ports/SATNJ001?utm_source=chatgpt.com)
    "محطة نفط تناجيب (Tanajib)": {"lat": 27.7948, "lon": 48.8921, "radius_km": 26},
}

# =========================
# Persistence (delta + alerts)
# =========================
STATE_FILE = "ais_ports_state.json"
TYPE_CACHE_FILE = "ais_type_cache.json"

# تنبيه ازدحام/تصاعد
ALERT_WAITING_SPIKE = 8   # إذا زاد المنتظرون في ميناء واحد مقارنة بالتشغيل السابق
WAITING_SPEED_KTS = 0.7   # أقل = غالباً انتظار/رسو

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
    msg = data.get("Message", {})
    for _, blk in msg.items():
        if isinstance(blk, dict) and ("Latitude" in blk) and ("Longitude" in blk):
            return float(blk["Latitude"]), float(blk["Longitude"]), blk
    raise KeyError

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
    sog = get_sog_knots(blk)
    nav = get_nav_status(blk)
    # شائع: 1=Anchored, 5=Moored
    if nav in (1, 5):
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

def congestion_level(total, waiting):
    if waiting >= 15 or total >= 50:
        return "🔴 شديد"
    if waiting >= 7 or total >= 25:
        return "🟠 مرتفع"
    if waiting >= 3 or total >= 10:
        return "🟡 متوسط"
    return "🟢 منخفض"

def run_capture():
    type_cache = load_json(TYPE_CACHE_FILE, {})  # mmsi -> type
    vessels = {}  # mmsi -> {lat,lon,waiting,type}

    samples_total = 0
    samples_pos = 0
    samples_static = 0

    def on_open(ws):
        # نفتح عالمي لتحسين فرصة التقاط الموانئ/المحطات (التغطية تختلف)
        ws.send(json.dumps({
            "APIKey": API_KEY,
            "BoundingBoxes": [[[-90.0, -180.0], [90.0, 180.0]]]
        }))

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
            lat, lon, blk = extract_lat_lon_and_block(data)
        except Exception:
            return

        samples_pos += 1

        # فلترة محلية: نخلي فقط اللي قريب من أي ميناء/محطة (radius + margin)
        near_any = False
        for p in PORTS.values():
            if haversine_km(p["lat"], p["lon"], lat, lon) <= (p["radius_km"] + 5):
                near_any = True
                break
        if not near_any:
            return

        vtype = blk.get("Type", 0) or type_cache.get(mmsi, 0)
        vessels[mmsi] = {
            "lat": lat,
            "lon": lon,
            "waiting": is_waiting(blk),
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
    return samples_total, samples_pos, samples_static, vessels

if __name__ == "__main__":
    prev_state = load_json(STATE_FILE, {"ports": {}, "ts": ""})

    total, pos, stat, vessels = run_capture()
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

📌 ملاحظة:
• التغطية تعتمد على توفر بث AIS قرب كل موقع.
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
