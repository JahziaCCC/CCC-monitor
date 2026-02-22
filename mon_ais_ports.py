import os
import json
import math
import time
import hashlib
from websocket import create_connection

AIS_KEY = os.environ.get("AISSTREAM_API_KEY", "").strip()

# موانئ + نصف قطر الرصد (KM)
PORTS = [
    {"name": "ميناء جدة الإسلامي", "lat": 21.49, "lon": 39.17, "radius_km": 35},
    {"name": "ميناء الملك عبدالعزيز (الدمام)", "lat": 26.46, "lon": 50.10, "radius_km": 35},
    {"name": "ميناء ينبع التجاري", "lat": 24.09, "lon": 38.06, "radius_km": 35},
    {"name": "ميناء الجبيل التجاري", "lat": 27.00, "lon": 49.65, "radius_km": 35},
]

# الأنواع التي نريدها (حسب توثيق aisstream: MessageType + Message + MetaData)  [oai_citation:1‡Aisstream](https://aisstream.io/documentation)
FILTER_TYPES = [
    "PositionReport",
    "StandardClassBPositionReport",
    "ExtendedClassBPositionReport",
]

CONGESTION_N = 30  # عتبة ازدحام

def _fp(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:24]

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d1 = math.radians(lat2 - lat1)
    d2 = math.radians(lon2 - lon1)
    a = (math.sin(d1/2)**2) + math.cos(p1) * math.cos(p2) * (math.sin(d2/2)**2)
    return 2 * R * math.asin(math.sqrt(a))

def _bbox_around(lat: float, lon: float, radius_km: float):
    # تقريب: 1 درجة عرض ≈ 111 كم
    dlat = radius_km / 111.0
    # 1 درجة طول ≈ 111 * cos(lat)
    dlon = radius_km / (111.0 * max(0.2, math.cos(math.radians(lat))))
    # صيغة BBOX في aisstream: [[[lat1, lon1],[lat2, lon2]]]  [oai_citation:2‡Aisstream](https://aisstream.io/documentation)
    return [[ [lat - dlat, lon - dlon], [lat + dlat, lon + dlon] ]]

def _extract_from_aisstream(msg: dict):
    """
    aisstream message format:
    {
      "MessageType": "...",
      "MetaData": {"MMSI":..., "latitude":..., "longitude":...},
      "Message": {"<MessageType>": {...}}
    }
    (قد تأتي Metadata بدل MetaData، وقد تأتي Latitude/Longitude بدل latitude/longitude)
     [oai_citation:3‡Aisstream](https://aisstream.io/documentation)
    """
    meta = msg.get("MetaData") or msg.get("Metadata") or msg.get("metaData") or {}
    if not isinstance(meta, dict):
        return None, None, None

    mmsi = meta.get("MMSI") or meta.get("mmsi")
    lat = meta.get("latitude") if "latitude" in meta else meta.get("Latitude")
    lon = meta.get("longitude") if "longitude" in meta else meta.get("Longitude")

    if mmsi is None or lat is None or lon is None:
        return None, None, None

    try:
        return str(int(mmsi)), float(lat), float(lon)
    except Exception:
        return None, None, None

def fetch(sample_seconds: int = 120):
    if not AIS_KEY:
        return []

    # نجمع counts لكل ميناء
    counts = {p["name"]: set() for p in PORTS}

    # BoundingBoxes صغيرة حول كل ميناء
    bboxes = []
    for p in PORTS:
        bboxes.append(_bbox_around(p["lat"], p["lon"], p["radius_km"])[0])

    subscription = {
        "APIKey": AIS_KEY,
        "BoundingBoxes": bboxes,
        "FilterMessageTypes": FILTER_TYPES,
    }

    try:
        ws = create_connection("wss://stream.aisstream.io/v0/stream", timeout=40)
        # مهم: لازم نرسل subscription خلال 3 ثواني من فتح الاتصال  [oai_citation:4‡Aisstream](https://aisstream.io/documentation)
        ws.send(json.dumps(subscription))

        t0 = time.time()
        while time.time() - t0 < sample_seconds:
            raw = ws.recv()
            if not raw:
                continue
            try:
                msg = json.loads(raw)
            except Exception:
                continue

            mmsi, lat, lon = _extract_from_aisstream(msg)
            if not mmsi:
                continue

            for p in PORTS:
                if haversine_km(lat, lon, p["lat"], p["lon"]) <= p["radius_km"]:
                    counts[p["name"]].add(mmsi)

        ws.close()
    except Exception:
        # لا نسقط التقرير إذا aisstream تعطل
        return []

    items = []
    for p in PORTS:
        port_name = p["name"]
        n = len(counts.get(port_name, set()))
        items.append({
            "key": _fp(f"port|{port_name}|{n}"),
            "section": "ports",
            "title": f"🚢 {port_name}: {n} سفينة داخل النطاق",
            "link": "https://aisstream.io/documentation",
            "meta": {
                "port": port_name,
                "count": n,
                "congested": n >= CONGESTION_N
            }
        })

    return items
