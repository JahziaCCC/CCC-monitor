import hashlib, requests

THRESH_PM10 = 200  # عتبة تشغيلية (عدّلها)

CITIES = [
    ("الرياض", 24.7136, 46.6753),
    ("جدة", 21.4858, 39.1925),
    ("الدمام", 26.4207, 50.0888),
    ("تبوك", 28.3838, 36.5550),
]

def _fp(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:24]

def fetch():
    items = []
    for name, lat, lon in CITIES:
        url = (
            "https://air-quality-api.open-meteo.com/v1/air-quality"
            f"?latitude={lat}&longitude={lon}&hourly=pm10&timezone=UTC"
        )
        r = requests.get(url, timeout=25)
        r.raise_for_status()
        data = r.json()
        pm10 = (data.get("hourly", {}).get("pm10") or [])
        if not pm10:
            continue
        max_pm10 = max(pm10[:48]) if len(pm10) >= 48 else max(pm10)
        if max_pm10 >= THRESH_PM10:
            title = f"🌪️ مؤشر غبار مرتفع — {name}: {max_pm10:.0f} µg/m³"
            items.append({
                "key": _fp("dust|" + title),
                "section": "dust",
                "title": title,
                "link": "https://open-meteo.com/en/docs/air-quality-api",
                "meta": {"city": name, "max_pm10": max_pm10}
            })
    return items
