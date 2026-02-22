import hashlib
import requests

THRESH_PM10 = 200  # عتبة تشغيلية (عدّلها)
PM10_HARD_CAP = 600  # ✅ سقف لتصفية القيم الشاذة (outliers)

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

        try:
            r = requests.get(url, timeout=25)
            r.raise_for_status()
            data = r.json()
        except Exception:
            continue

        pm10 = (data.get("hourly", {}).get("pm10") or [])
        if not pm10:
            continue

        # ✅ ناخذ أعلى قيمة في آخر 48 ساعة (أو أقل) ثم نطبق سقف منطقي
        window = pm10[:48] if len(pm10) >= 48 else pm10
        max_pm10 = max(window)
        max_pm10 = min(max_pm10, PM10_HARD_CAP)

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
