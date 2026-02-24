# mon_firms.py
import os
import requests
import math

# (اختياري) مدن مرجعية لحساب "قرب من"
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
    """
    Returns a list of events (dicts) with:
      { "section": "fires", "title": "..." }
    IMPORTANT:
      - If no fires => return []  (NOT "لا يوجد" message)
    """

    key = os.environ.get("FIRMS_MAP_KEY", "").strip()
    if not key:
        # لا تعتبره حدث حرائق.. هذا مجرد تعطيل/نقص إعدادات
        return [{
            "section": "fires",
            "title": "ℹ️ FIRMS غير مفعّل: ضع FIRMS_MAP_KEY."
        }]

    # NASA FIRMS "country csv" (آخر 24 ساعة عادة حسب الـ endpoint)
    url = f"https://firms.modaps.eosdis.nasa.gov/api/country/csv/{key}/VIIRS_SNPP_NRT/SAU/1"

    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()

        lines = r.text.splitlines()
        if len(lines) <= 1:
            # ✅ لا توجد حرائق = لا نرجع أي events
            return []

        rows = []
        for row in lines[1:]:
            cols = row.split(",")
            # حسب صيغة FIRMS country csv:
            # 0 lat, 1 lon ... 11 frp
            lat = float(cols[0])
            lon = float(cols[1])
            frp = float(cols[11])
            rows.append((lat, lon, frp))

        # ترتيب حسب FRP
        rows.sort(key=lambda x: x[2], reverse=True)

        total = len(rows)
        max_frp = max(x[2] for x in rows)
        top5 = rows[:5]

        events = [{
            "section": "fires",
            "title": f"🔥 حرائق نشطة داخل السعودية — {total} رصد خلال آخر 24 ساعة (أعلى FRP: {max_frp})"
        }]

        for i, (lat, lon, frp) in enumerate(top5, 1):
            city, dist = _nearest_city(lat, lon)
            events.append({
                "section": "fires",
                "title": (
                    f"📍 نقطة #{i}: قرب {city} (~{dist} كم) | {lat},{lon} | FRP {frp} | "
                    f"https://maps.google.com/?q={lat},{lon}"
                )
            })

        return events

    except Exception as e:
        return [{
            "section": "fires",
            "title": f"ℹ️ تعذر جلب بيانات FIRMS مؤقتاً ({type(e).__name__})"
        }]
