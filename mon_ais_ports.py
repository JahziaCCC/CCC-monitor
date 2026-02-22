import os
import requests
import hashlib

AIS_KEY = os.environ.get("AISSTREAM_API_KEY", "").strip()

PORTS = [
    {"name": "ميناء جدة الإسلامي", "lat": 21.49, "lon": 39.17},
    {"name": "ميناء الملك عبدالعزيز (الدمام)", "lat": 26.46, "lon": 50.10},
    {"name": "ميناء ينبع التجاري", "lat": 24.09, "lon": 38.06},
    {"name": "ميناء الجبيل التجاري", "lat": 27.00, "lon": 49.65},
]

CONGESTION_N = 30

def _fp(s):
    return hashlib.sha256(s.encode()).hexdigest()[:24]

def fetch(sample_seconds=120):

    if not AIS_KEY:
        return []

    items = []

    headers = {
        "Authorization": AIS_KEY
    }

    for p in PORTS:

        # AISStream REST endpoint (آخر السفن حول نقطة)
        url = (
            "https://api.aisstream.io/v0/ships"
            f"?latitude={p['lat']}"
            f"&longitude={p['lon']}"
            "&radius=40"
        )

        try:
            r = requests.get(url, headers=headers, timeout=25)
            r.raise_for_status()
            data = r.json()
        except Exception:
            continue

        ships = data.get("ships", [])
        n = len(ships)

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
