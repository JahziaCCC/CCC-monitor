# mon_firms.py
import os
import requests
import math

CITIES = {
    "الرياض": (24.7136, 46.6753),
    "جدة": (21.5433, 39.1728),
    "الدمام": (26.4207, 50.0888),
    "الجبيل": (27.0174, 49.6583),
    "مكة": (21.3891, 39.8579),
    "المدينة": (24.5247, 39.5692),
}

def _distance_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def _nearest_city(lat, lon):
    best_city = None
    best_d = 10**9
    for city, (clat, clon) in CITIES.items():
        d = _distance_km(lat, lon, clat, clon)
        if d < best_d:
            best_city = city
            best_d = d
    return best_city, int(best_d)

def get_events():
    key = os.environ.get("FIRMS_MAP_KEY", "").strip()
    if not key:
        return [{"section": "fires", "title": "ℹ️ FIRMS غير مفعّل: ضع FIRMS_MAP_KEY."}]

    url = f"https://firms.modaps.eosdis.nasa.gov/api/country/csv/{key}/VIIRS_SNPP_NRT/SAU/1"

    r = requests.get(url, timeout=30)
    r.raise_for_status()

    lines = r.text.splitlines()
    if len(lines) <= 1:
        # ✅ لا يوجد حرائق => نرجّع [] (بدون حدث)
        return []

    rows = []
    for row in lines[1:]:
        cols = row.split(",")
        lat = float(cols[0])
        lon = float(cols[1])
        frp = float(cols[11])
        acq_date = cols[5] if len(cols) > 5 else ""
        acq_time = cols[6] if len(cols) > 6 else ""
        rows.append((lat, lon, frp, acq_date, acq_time))

    rows.sort(key=lambda x: x[2], reverse=True)

    total = len(rows)
    max_frp = max(x[2] for x in rows)
    top5 = rows[:5]

    events = [{
        "section": "fires",
        "title": f"🔥 حرائق نشطة داخل السعودية — {total} رصد خلال آخر 24 ساعة (أعلى FRP: {max_frp})"
    }]

    for i, (lat, lon, frp, d, t) in enumerate(top5, 1):
        city, dist = _nearest_city(lat, lon)
        when = f"{d} {t} UTC".strip()
        events.append({
            "section": "fires",
            "title": (
                f"📍 نقطة #{i}: قرب {city} (~{dist} كم) | {lat},{lon} | FRP {frp} | {when} | "
                f"https://maps.google.com/?q={lat},{lon}"
            )
        })

    return events
