# mon_firms.py
import os
import requests
import math

# مدن مرجعية
CITIES = {
    "الرياض": (24.7136, 46.6753),
    "جدة": (21.5433, 39.1728),
    "الدمام": (26.4207, 50.0888),
    "الجبيل": (27.0174, 49.6583),
}

def distance_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2-lat1)
    dlon = math.radians(lon2-lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def nearest_city(lat, lon):
    best = None
    best_d = 99999
    for c,(clat,clon) in CITIES.items():
        d = distance_km(lat, lon, clat, clon)
        if d < best_d:
            best = c
            best_d = d
    return best, int(best_d)

def get_events():

    key = os.environ.get("FIRMS_MAP_KEY","")

    if not key:
        return [{
            "section":"fires",
            "title":"ℹ️ FIRMS غير مفعّل: ضع FIRMS_MAP_KEY."
        }]

    url = f"https://firms.modaps.eosdis.nasa.gov/api/country/csv/{key}/VIIRS_SNPP_NRT/SAU/1"

    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()

        lines = r.text.splitlines()

        if len(lines) <= 1:
            return [{
                "section":"fires",
                "title":"لا يوجد حرائق نشطة حالياً."
            }]

        data = []
        for row in lines[1:]:
            cols = row.split(",")
            lat = float(cols[0])
            lon = float(cols[1])
            frp = float(cols[11])
            data.append((lat,lon,frp))

        data.sort(key=lambda x: x[2], reverse=True)

        top = data[:5]
        max_frp = max(x[2] for x in data)

        events = []

        events.append({
            "section":"fires",
            "title":f"🔥 حرائق نشطة داخل السعودية — {len(data)} رصد خلال آخر 24 ساعة (أعلى FRP: {max_frp})"
        })

        for i,(lat,lon,frp) in enumerate(top,1):
            city,dist = nearest_city(lat,lon)

            events.append({
                "section":"fires",
                "title":f"📍 نقطة #{i}: قرب {city} (~{dist} كم) | {lat},{lon} | FRP {frp} | https://maps.google.com/?q={lat},{lon}"
            })

        return events

    except Exception as e:
        return [{
            "section":"fires",
            "title":f"ℹ️ تعذر جلب بيانات FIRMS مؤقتاً ({type(e).__name__})"
        }]
