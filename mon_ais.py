# mon_ais.py
import os
import json
import time
import math
import requests

PORTS = [
    ("ميناء جدة الإسلامي", 21.49, 39.17, 25),
    ("ميناء الملك عبدالعزيز (الدمام)", 26.44, 50.10, 25),
    ("ميناء ينبع التجاري", 24.09, 38.06, 25),
    ("ميناء الجبيل التجاري", 27.00, 49.65, 25),
]

AISSTREAM_API_KEY = os.environ.get("AISSTREAM_API_KEY", "").strip()
AISSTREAM_SECONDS = int(os.environ.get("AISSTREAM_SECONDS", "25"))
AISSTREAM_WSS = os.environ.get("AISSTREAM_WSS", "wss://stream.aisstream.io/v0/stream")

AIS_API_KEY = os.environ.get("AIS_API_KEY", "").strip()
AIS_BASE_URL = os.environ.get("AIS_BASE_URL", "").strip()

def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p = math.pi / 180.0
    dlat = (lat2 - lat1) * p
    dlon = (lon2 - lon1) * p
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))

def _ports_counter():
    return {name: set() for name, *_ in PORTS}

def _count_ship_in_ports(counter, mmsi, lat, lon):
    if lat is None or lon is None:
        return
    for name, plat, plon, rkm in PORTS:
        if _haversine_km(plat, plon, lat, lon) <= rkm:
            counter[name].add(str(mmsi))

def _build_events(counter):
    out = []
    for name, *_ in PORTS:
        out.append({"section": "ais", "title": f"🚢 {name}: {len(counter[name])} سفينة داخل النطاق"})
    return out

def _aisstream_collect():
    try:
        import websocket  # websocket-client
    except Exception:
        return [{"section": "ais", "title": "ℹ️ AISStream يحتاج websocket-client (أضفها في requirements.txt)."}]

    counter = _ports_counter()
    t_end = time.time() + AISSTREAM_SECONDS

    sub_msg = {
        "APIKey": AISSTREAM_API_KEY,
        "BoundingBoxes": [[[-90, -180], [90, 180]]],
        "FilterMessageTypes": ["PositionReport"]
    }

    ws = websocket.create_connection(AISSTREAM_WSS, timeout=20)
    ws.send(json.dumps(sub_msg))
    ws.settimeout(3)

    while time.time() < t_end:
        try:
            raw = ws.recv()
            msg = json.loads(raw)

            m = (msg.get("Message") or {}).get("PositionReport") or {}
            meta = (msg.get("MetaData") or msg.get("MetaData") or {}) or {}

            lat = m.get("Latitude")
            lon = m.get("Longitude")
            mmsi = meta.get("MMSI") or m.get("UserID") or meta.get("MMSIString")
            if not mmsi:
                continue

            _count_ship_in_ports(counter, mmsi, lat, lon)

        except Exception:
            continue

    try:
        ws.close()
    except Exception:
        pass

    return _build_events(counter)

def _http_provider_collect():
    if not AIS_BASE_URL:
        return [{"section": "ais", "title": "ℹ️ AIS غير مفعّل: ضع AISSTREAM_API_KEY أو AIS_BASE_URL + AIS_API_KEY."}]

    counter = _ports_counter()

    for name, plat, plon, rkm in PORTS:
        try:
            r = requests.get(
                AIS_BASE_URL,
                headers={"Authorization": f"Bearer {AIS_API_KEY}"} if AIS_API_KEY else {},
                params={"lat": plat, "lon": plon, "radius_km": rkm},
                timeout=40
            )
            r.raise_for_status()
            data = r.json()
            ships = data.get("ships") or data.get("data") or []

            for s in ships:
                mmsi = s.get("mmsi") or s.get("MMSI") or s.get("id")
                lat = s.get("lat") or s.get("latitude")
                lon = s.get("lon") or s.get("longitude")
                if mmsi and lat is not None and lon is not None:
                    _count_ship_in_ports(counter, mmsi, float(lat), float(lon))
        except Exception:
            continue

    return _build_events(counter)

def get_events():
    if AISSTREAM_API_KEY:
        return _aisstream_collect()
    return _http_provider_collect()
