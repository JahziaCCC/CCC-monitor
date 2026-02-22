import os, json, math, time, hashlib
from websocket import create_connection

AIS_KEY = os.environ.get("AISSTREAM_API_KEY", "").strip()

BBOX = {"min_lat": 10.0, "max_lat": 38.0, "min_lon": 32.0, "max_lon": 61.0}
PORTS = [
    {"name": "ميناء جدة الإسلامي", "lat": 21.49, "lon": 39.17, "radius_km": 25},
    {"name": "ميناء الملك عبدالعزيز (الدمام)", "lat": 26.46, "lon": 50.10, "radius_km": 25},
]
CONGESTION_N = 30

def _fp(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:24]

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d1 = math.radians(lat2-lat1); d2 = math.radians(lon2-lon1)
    a = math.sin(d1/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(d2/2)**2
    return 2*R*math.asin(math.sqrt(a))

def fetch(sample_seconds=60):
    if not AIS_KEY:
        return []

    ws = create_connection("wss://stream.aisstream.io/v0/stream", timeout=20)
    ws.send(json.dumps({
        "APIKey": AIS_KEY,
        "BoundingBoxes": [[[BBOX["min_lat"], BBOX["min_lon"]],[BBOX["max_lat"], BBOX["max_lon"]]]]
    }))

    counts = {p["name"]: set() for p in PORTS}
    t0 = time.time()

    while time.time() - t0 < sample_seconds:
        msg = json.loads(ws.recv())
        mmsi = msg.get("MMSI") or msg.get("mmsi")
        pos = msg.get("PositionReport") or msg.get("positionReport") or msg.get("message", {}).get("PositionReport")
        if not mmsi or not isinstance(pos, dict):
            continue
        lat = pos.get("Latitude") or pos.get("lat")
        lon = pos.get("Longitude") or pos.get("lon")
        if lat is None or lon is None:
            continue

        for p in PORTS:
            if haversine_km(float(lat), float(lon), p["lat"], p["lon"]) <= p["radius_km"]:
                counts[p["name"]].add(str(mmsi))

    ws.close()

    items = []
    for port, ships in counts.items():
        n = len(ships)
        title = f"🚢 {port}: {n} سفينة داخل النطاق"
        items.append({
            "key": _fp(f"port|{port}|{n}"),
            "section": "ports",
            "title": title,
            "link": "https://aisstream.io/",
            "meta": {"port": port, "count": n, "congested": n >= CONGESTION_N}
        })
    return items
