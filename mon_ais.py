# mon_ais.py
import os
import requests

AIS_API_KEY = os.environ.get("AIS_API_KEY", "")
AIS_BASE_URL = os.environ.get("AIS_BASE_URL", "")  # ضع رابط مزود AIS عندك

PORTS = [
    ("ميناء جدة الإسلامي", 21.49, 39.17, 25),
    ("ميناء الملك عبدالعزيز (الدمام)", 26.44, 50.10, 25),
    ("ميناء ينبع التجاري", 24.09, 38.06, 25),
    ("ميناء الجبيل التجاري", 27.00, 49.65, 25),
]

def get_events():
    if not AIS_API_KEY or not AIS_BASE_URL:
        return [{"section": "ais", "title": "ℹ️ AIS غير مفعّل: ضع AIS_API_KEY و AIS_BASE_URL."}]

    events = []

    # مثال عام (لازم توائم params حسب مزودك)
    for name, lat, lon, radius_km in PORTS:
        try:
            r = requests.get(
                AIS_BASE_URL,
                headers={"Authorization": f"Bearer {AIS_API_KEY}"},
                params={"lat": lat, "lon": lon, "radius_km": radius_km},
                timeout=40
            )
            r.raise_for_status()
            data = r.json()
            ships = data.get("ships") or []
            events.append({
                "section": "ais",
                "title": f"🚢 {name}: {len(ships)} سفينة داخل النطاق"
            })
        except Exception:
            events.append({"section": "ais", "title": f"⚠️ تعذر جلب AIS — {name} (مؤقتاً)."})
    return events
