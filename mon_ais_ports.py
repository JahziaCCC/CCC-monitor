import os
import json
import math
import time
import hashlib
from websocket import create_connection

AIS_KEY = os.environ.get("AISSTREAM_API_KEY", "").strip()

PORTS = [
    {"name": "ميناء جدة الإسلامي", "lat": 21.49, "lon": 39.17, "radius_km": 35},
    {"name": "ميناء الملك عبدالعزيز (الدمام)", "lat": 26.46, "lon": 50.10, "radius_km": 35},
    {"name": "ميناء ينبع التجاري", "lat": 24.09, "lon": 38.06, "radius_km": 35},
    {"name": "ميناء الجبيل التجاري", "lat": 27.00, "lon": 49.65, "radius_km": 35},
]

CONGESTION_N = 30

def _fp(s):
    return hashlib.sha256(s.encode()).hexdigest()[:24]

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d1 = math.radians(lat2-lat1)
    d2 = math.radians(lon2-lon1)
    a = math.sin(d1/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(d2/2)**2
    return 2*R*math.asin(math.sqrt(a))

def extract_position(msg):
    """
    يدعم جميع أنواع AIS position reports
    """
    mmsi = msg.get("MMSI")

    message = msg.get("Message") or msg.get("message") or {}

    pos = (
        message.get("PositionReport")
        or message.get("PositionReportClassA")
        or message.get("PositionReportClassB")
        or message.get("StandardClassBPositionReport")
    )

    if not mmsi or not isinstance(pos, dict):
        return None, None, None

    lat = pos.get("Latitude")
    lon = pos.get("Longitude")

    if lat is None or lon is None:
        return None, None, None

    return str(mmsi), float(lat), float(lon)

def fetch(sample_seconds=120):

    if not AIS_KEY:
        return []

    counts = {p["name"]: set() for p in PORTS}

    try:
        ws = create_connection("wss://stream.aisstream.io/v0/stream", timeout=40)

        ws.send(json.dumps({
            "APIKey": AIS_KEY,
            "BoundingBoxes": [[[-90,-180],[90,180]]]
        }))

        start = time.time()

        while time.time() - start < sample_seconds:

            raw = ws.recv()
            if not raw:
                continue

            try:
                msg = json.loads(raw)
            except:
                continue

            mmsi, lat, lon = extract_position(msg)
            if not mmsi:
                continue

            for p in PORTS:
                if haversine(lat, lon, p["lat"], p["lon"]) <= p["radius_km"]:
                    counts[p["name"]].add(mmsi)

        ws.close()

    except Exception:
        return []

    items = []

    for p in PORTS:
        n = len(counts[p["name"]])
        items.append({
            "key": _fp(f"{p['name']}|{n}"),
            "section": "ports",
            "title": f"🚢 {p['name']}: {n} سفينة داخل النطاق",
            "link": "https://aisstream.io/",
            "meta": {
                "port": p["name"],
                "count": n,
                "congested": n >= CONGESTION_N
            }
        })

    return items
