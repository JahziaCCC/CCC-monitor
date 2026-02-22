import os
import json
import math
import time
import hashlib
from websocket import create_connection

AIS_KEY = os.environ.get("AISSTREAM_API_KEY", "").strip()

# نطاق السعودية + الجوار + البحر الأحمر/الخليج (قابل للتعديل)
BBOX = {"min_lat": 10.0, "max_lat": 38.0, "min_lon": 32.0, "max_lon": 61.0}

# موانئ مستهدفة (قابل للتعديل)
PORTS = [
    {"name": "ميناء جدة الإسلامي", "lat": 21.49, "lon": 39.17, "radius_km": 25},
    {"name": "ميناء الملك عبدالعزيز (الدمام)", "lat": 26.46, "lon": 50.10, "radius_km": 25},
    {"name": "ميناء ينبع التجاري", "lat": 24.09, "lon": 38.06, "radius_km": 25},
]

CONGESTION_N = 30  # عتبة "ازدحام"

def _fp(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:24]

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d1 = math.radians(lat2 - lat1)
    d2 = math.radians(lon2 - lon1)
    a = (math.sin(d1/2)**2) + math.cos(p1) * math.cos(p2) * (math.sin(d2/2)**2)
    return 2 * R * math.asin(math.sqrt(a))

def _extract_position(msg: dict):
    """
    يحاول استخراج lat/lon من أكثر من شكل للرسالة.
    """
    mmsi = msg.get("MMSI") or msg.get("mmsi")
    pos = (
        msg.get("PositionReport")
        or msg.get("positionReport")
        or (msg.get("message") or {}).get("PositionReport")
        or (msg.get("message") or {}).get("positionReport")
    )
    if not mmsi or not isinstance(pos, dict):
        return None, None, None

    lat = pos.get("Latitude") if "Latitude" in pos else pos.get("lat")
    lon = pos.get("Longitude") if "Longitude" in pos else pos.get("lon")

    if lat is None or lon is None:
        return None, None, None

    try:
        return str(mmsi), float(lat), float(lon)
    except Exception:
        return None, None, None

def fetch(sample_seconds: int = 120):
    """
    يجمع عدد السفن داخل نطاق نصف قطر حول كل ميناء خلال sample_seconds.
    - إذا لا يوجد مفتاح أو فشل الاتصال: يرجع [] بدون إسقاط التشغيل.
    """
    if not AIS_KEY:
        return []

    # مجموعة MMSI لكل ميناء
    counts = {p["name"]: set() for p in PORTS}

    try:
        ws = create_connection("wss://stream.aisstream.io/v0/stream", timeout=35)
        ws.send(json.dumps({
            "APIKey": AIS_KEY,
            "BoundingBoxes": [[[BBOX["min_lat"], BBOX["min_lon"]], [BBOX["max_lat"], BBOX["max_lon"]]]]
        }))

        t0 = time.time()
        while time.time() - t0 < sample_seconds:
            raw = ws.recv()
            if not raw:
                continue

            try:
                msg = json.loads(raw)
            except Exception:
                continue

            mmsi, lat, lon = _extract_position(msg)
            if not mmsi:
                continue

            for p in PORTS:
                if haversine_km(lat, lon, p["lat"], p["lon"]) <= p["radius_km"]:
                    counts[p["name"]].add(mmsi)

        ws.close()

    except Exception:
        # لا نسقط التقرير إذا AISStream تعطل
        return []

    items = []
    for p in PORTS:
        port = p["name"]
        n = len(counts.get(port, set()))
        items.append({
            "key": _fp(f"port|{port}|{n}"),
            "section": "ports",
            "title": f"🚢 {port}: {n} سفينة داخل النطاق",
            "link": "https://aisstream.io/",
            "meta": {"port": port, "count": n, "congested": n >= CONGESTION_N}
        })

    return items
