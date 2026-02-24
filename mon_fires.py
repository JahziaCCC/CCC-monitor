# mon_firms.py
import os
import datetime
import math
import requests

# ===== إعدادات =====
FIRMS_MAP_KEY = os.environ.get("FIRMS_MAP_KEY", "")
FIRMS_SOURCE = os.environ.get("FIRMS_SOURCE", "VIIRS_SNPP_NRT")  # أو VIIRS_NOAA20_NRT
FIRMS_DAYS = int(os.environ.get("FIRMS_DAYS", "1"))              # آخر كم يوم
FIRMS_TIMEOUT = int(os.environ.get("FIRMS_TIMEOUT", "25"))

# نطاق السعودية التقريبي (يمكن تغييره)
KSA_BBOX = (33.0, 14.5, 57.5, 33.8)  # west, south, east, north

UTC = datetime.timezone.utc

# مدن/مناطق مرجعية داخل السعودية (وسعها براحتك)
CITIES = {
    "الرياض": (24.7136, 46.6753),
    "مكة": (21.3891, 39.8579),
    "المدينة": (24.5247, 39.5692),
    "جدة": (21.5433, 39.1728),
    "الدمام": (26.4207, 50.0888),
    "الجبيل": (27.0046, 49.6460),
    "الأحساء": (25.3830, 49.5866),
    "تبوك": (28.3998, 36.5715),
    "حائل": (27.5114, 41.7208),
    "عرعر": (30.9753, 41.0381),
    "سكاكا": (29.9697, 40.2064),
    "أبها": (18.2164, 42.5053),
    "جازان": (16.8892, 42.5706),
    "نجران": (17.5650, 44.2289),
    "الباحة": (20.0129, 41.4677),
    "القصيم (بريدة)": (26.3592, 43.9818),
    "العلا": (26.6086, 37.9232),
    "نيوم": (28.2683, 35.2020),
}

def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return r * c

def _nearest_city(lat, lon):
    best_name, best_km = None, 10**9
    for name, (clat, clon) in CITIES.items():
        d = _haversine_km(lat, lon, clat, clon)
        if d < best_km:
            best_name, best_km = name, d
    return best_name, best_km

def _firms_url():
    # API FIRMS: CSV داخل bbox
    # مثال:
    # https://firms.modaps.eosdis.nasa.gov/api/area/csv/<MAP_KEY>/<SOURCE>/<WEST,SOUTH,EAST,NORTH>/<DAYS>/
    if not FIRMS_MAP_KEY:
        return None
    w, s, e, n = KSA_BBOX
    bbox = f"{w},{s},{e},{n}"
    return f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{FIRMS_MAP_KEY}/{FIRMS_SOURCE}/{bbox}/{FIRMS_DAYS}/"

def _parse_csv(text: str):
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return []

    header = lines[0].split(",")
    idx = {k: i for i, k in enumerate(header)}

    def g(row, key, default=""):
        i = idx.get(key)
        if i is None or i >= len(row):
            return default
        return row[i]

    out = []
    for ln in lines[1:]:
        row = ln.split(",")
        try:
            lat = float(g(row, "latitude"))
            lon = float(g(row, "longitude"))
        except Exception:
            continue

        try:
            frp = float(g(row, "frp", "0") or 0)
        except Exception:
            frp = 0.0

        # وقت/تاريخ
        acq_date = g(row, "acq_date", "")
        acq_time = g(row, "acq_time", "")
        ts = f"{acq_date} {acq_time}".strip()

        out.append({
            "lat": lat,
            "lon": lon,
            "frp": frp,
            "ts": ts
        })
    return out

def get_events():
    """
    يرجع Events لقسم fires بالشكل المتوافق مع report_official.py:
    [
      {"section":"fires","title":"..."}
    ]
    """
    url = _firms_url()
    if not url:
        return [{
            "section": "fires",
            "title": "ℹ️ FIRMS غير مفعّل: ضع FIRMS_MAP_KEY."
        }]

    try:
        r = requests.get(url, timeout=FIRMS_TIMEOUT)
        r.raise_for_status()
        rows = _parse_csv(r.text)

        if not rows:
            return []

        # احصائيات
        count = len(rows)
        max_frp = max(x["frp"] for x in rows) if rows else 0.0

        # خذ أعلى 5 نقاط حسب FRP
        top = sorted(rows, key=lambda x: x["frp"], reverse=True)[:5]

        events = []
        events.append({
            "section": "fires",
            "title": f"🔥 حرائق نشطة داخل السعودية — {count} رصد خلال آخر 24 ساعة (أعلى FRP: {max_frp:.1f})"
        })

        for i, p in enumerate(top, start=1):
            city, km = _nearest_city(p["lat"], p["lon"])
            maps = f"https://maps.google.com/?q={p['lat']:.5f},{p['lon']:.5f}"
            events.append({
                "section": "fires",
                "title": (
                    f"📍 نقطة #{i}: قرب {city} (~{km:.0f} كم) | "
                    f"{p['lat']:.5f},{p['lon']:.5f} | FRP {p['frp']:.1f} | {p['ts']} | {maps}"
                )
            })

        return events

    except Exception as e:
        return [{
            "section": "fires",
            "title": f"ℹ️ ملاحظة: تعذر جلب بيانات FIRMS مؤقتاً. ({type(e).__name__})"
        }]
