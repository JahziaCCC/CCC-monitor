# mon_fires.py
import os
import io
import csv
import math
import requests

# ===== FIRMS API =====
# Docs: https://firms.modaps.eosdis.nasa.gov/content/academy/data_api/firms_api_use.html
FIRMS_AREA_CSV = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{source}/{bbox}/{days}"

# BBOX واسع لجلب البيانات، ثم نفلترها “فعلياً” داخل السعودية
# (خليه واسع شوي عشان ما يفوتك شيء، الفلتر هو اللي يقرر)
KSA_BBOX = os.environ.get("FIRMS_KSA_BBOX", "34.4,16.0,55.7,32.2")

FIRMS_SOURCE = os.environ.get("FIRMS_SOURCE", "VIIRS_SNPP_NRT")
FIRMS_DAYS = int(os.environ.get("FIRMS_DAYS", "1"))  # 1 = آخر 24 ساعة

TOP_N = int(os.environ.get("FIRMS_TOP_N", "5"))       # أكثر 5 نقاط FRP
MIN_FRP = float(os.environ.get("ALERT_FIRES_FRP", "0"))  # فلتر FRP (اختياري)

# وضع جغرافي:
# IN_KSA = داخل السعودية فقط (افتراضي)
# AROUND_KSA = داخل + حول السعودية بمسافة (KM)
GEO_MODE = os.environ.get("FIRMS_GEO_MODE", "IN_KSA").upper()
AROUND_KM = float(os.environ.get("FIRMS_AROUND_KM", "120"))

# نقاط مرجعية للتقريب (لعبارة "قرب ... (~كم)")
REF_PLACES = {
    "الرياض": (24.7136, 46.6753),
    "مكة": (21.3891, 39.8579),
    "المدينة": (24.5247, 39.5692),
    "جدة": (21.5433, 39.1728),
    "الدمام": (26.4207, 50.0888),
    "تبوك": (28.3998, 36.5715),
    "أبها": (18.2164, 42.5053),
    "جازان": (16.8892, 42.5706),
    "نجران": (17.5650, 44.2289),
    "حائل": (27.5114, 41.7208),
    "عرعر": (30.9753, 41.0381),
    "سكاكا": (29.9697, 40.2064),
    "القريات": (31.3317, 37.3428),
    "العلا": (26.6085, 37.9232),
    "نيوم": (27.9678, 35.2137),
    "بريدة": (26.3592, 43.9818),
}

def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2) + math.cos(p1)*math.cos(p2)*(math.sin(dlon/2)**2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def _nearest_place(lat, lon):
    best = None
    best_d = 10**9
    for name, (plat, plon) in REF_PLACES.items():
        d = _haversine_km(lat, lon, plat, plon)
        if d < best_d:
            best_d = d
            best = name
    return best, best_d

def _maps_link(lat, lon):
    return f"https://maps.google.com/?q={lat:.5f},{lon:.5f}"

def _parse_firms_csv(text):
    f = io.StringIO(text)
    reader = csv.DictReader(f)
    rows = []
    for r in reader:
        try:
            lat = float(r.get("latitude"))
            lon = float(r.get("longitude"))
            frp = float(r.get("frp")) if r.get("frp") not in (None, "", "nan") else 0.0
            acq_date = (r.get("acq_date") or "").strip()
            acq_time = (r.get("acq_time") or "").strip()
            rows.append({
                "lat": lat,
                "lon": lon,
                "frp": frp,
                "acq_date": acq_date,
                "acq_time": acq_time
            })
        except Exception:
            continue
    return rows

# ✅ فلتر “حدود السعودية التقريبي” (Polygon مبسط)
# الهدف: نتخلص من نقاط العراق/إيران اللي تطلع داخل الـ BBOX
def _in_ksa_polygon(lat, lon) -> bool:
    # فلتر أولي (مستطيل عام)
    if not (16.0 <= lat <= 32.2 and 34.4 <= lon <= 55.7):
        return False

    # استبعاد شمال شرق (يجيب العراق/إيران بسهولة)
    # مثال: lat>29.5 & lon>46 غالباً خارج السعودية
    if lat > 29.5 and lon > 46.0:
        return False

    # استبعاد أقصى الشرق (خارج السعودية/الخليج)
    if lon > 52.5:
        return False

    # استبعاد جنوب شرق (زوايا عمان/اليمن الزائدة)
    if lat < 17.0 and lon > 50.0:
        return False

    return True

def _distance_to_ksa_bbox(lat, lon):
    lon_min, lat_min, lon_max, lat_max = [float(x) for x in KSA_BBOX.split(",")]
    clamped_lat = min(max(lat, lat_min), lat_max)
    clamped_lon = min(max(lon, lon_min), lon_max)
    return _haversine_km(lat, lon, clamped_lat, clamped_lon)

def fetch():
    """
    Events لعرضها في التقرير:
    - سطر ملخص
    - TOP_N نقاط: أقرب مدينة + إحداثيات + FRP + وقت + رابط خرائط
    """
    key = os.environ.get("FIRMS_MAP_KEY", "").strip()
    if not key:
        return [{
            "section": "fires",
            "title": "⚠️ FIRMS: لا يوجد FIRMS_MAP_KEY في Secrets/Environment.",
            "meta": {}
        }]

    url = FIRMS_AREA_CSV.format(key=key, source=FIRMS_SOURCE, bbox=KSA_BBOX, days=FIRMS_DAYS)

    try:
        r = requests.get(url, timeout=45)
        r.raise_for_status()
    except Exception as e:
        return [{
            "section": "fires",
            "title": f"⚠️ FIRMS: تعذر جلب البيانات: {e}",
            "meta": {"url": url}
        }]

    rows = _parse_firms_csv(r.text)

    # فلتر FRP (اختياري)
    if MIN_FRP > 0:
        rows = [x for x in rows if x["frp"] >= MIN_FRP]

    # فلترة جغرافية: داخل السعودية فعلياً
    filtered = []
    for x in rows:
        inside = _in_ksa_polygon(x["lat"], x["lon"])
        if GEO_MODE == "IN_KSA":
            if inside:
                filtered.append(x)
        else:
            # AROUND_KSA: داخل السعودية + حولها بمسافة
            if inside:
                filtered.append(x)
            else:
                d = _distance_to_ksa_bbox(x["lat"], x["lon"])
                if d <= AROUND_KM:
                    x["dist_to_ksa_km"] = d
                    filtered.append(x)

    rows = filtered

    if not rows:
        return [{"section": "fires", "title": "- لا يوجد", "meta": {"count": 0}}]

    count = len(rows)
    max_frp = max(x["frp"] for x in rows)

    # أعلى نقاط حسب FRP
    top = sorted(rows, key=lambda x: x["frp"], reverse=True)[:TOP_N]

    scope_text = "داخل السعودية" if GEO_MODE == "IN_KSA" else f"داخل/حول السعودية (≤ {AROUND_KM:.0f} كم)"

    events = []

    # سطر ملخص
    events.append({
        "section": "fires",
        "title": f"🔥 حرائق نشطة {scope_text} — {count} رصد خلال آخر {FIRMS_DAYS*24} ساعة (أعلى FRP: {max_frp:.1f})",
        "meta": {"count": count, "max_frp": max_frp, "scope": scope_text, "bbox": KSA_BBOX, "source": FIRMS_SOURCE}
    })

    # تفاصيل وين
    for i, p in enumerate(top, start=1):
        place, dist = _nearest_place(p["lat"], p["lon"])
        link = _maps_link(p["lat"], p["lon"])
        ts = f"{p['acq_date']} {p['acq_time']} UTC".strip()

        events.append({
            "section": "fires",
            "title": f"📍 نقطة #{i}: قرب {place} (~{dist:.0f} كم) | {p['lat']:.5f},{p['lon']:.5f} | FRP {p['frp']:.1f} | {ts} | {link}",
            "meta": {"place": place, "dist_km": dist, **p, "link": link}
        })

    return events
