# mon_fires.py
import os
import csv
import io
import math
import datetime
import requests


# ========= إعدادات عامة =========
FIRMS_MAP_KEY = os.environ.get("FIRMS_MAP_KEY", "").strip()

# أفضل مصدر عملي عادةً: VIIRS (دقة أعلى من MODIS)
# مصادر FIRMS المقبولة مذكورة في صفحة API Area  [oai_citation:2‡firms.modaps.eosdis.nasa.gov](https://firms.modaps.eosdis.nasa.gov/api/area/)
FIRMS_SOURCE = os.environ.get("FIRMS_SOURCE", "VIIRS_SNPP_NRT").strip()

# نطاق السعودية (bbox): west,south,east,north
# تقدر تغيّرها لاحقاً لو تبغى توسع للجوار
KSA_BBOX = os.environ.get("FIRMS_BBOX", "34.4,16.0,55.7,32.3").strip()

# FIRMS يسمح 1..5 أيام بالطلب الواحد  [oai_citation:3‡firms.modaps.eosdis.nasa.gov](https://firms.modaps.eosdis.nasa.gov/api/area/)
DAY_RANGE = int(os.environ.get("FIRMS_DAY_RANGE", "1").strip() or "1")  # 1=آخر يوم

# عدد النقاط التفصيلية المعروضة في التقرير
TOP_POINTS = int(os.environ.get("FIRMS_TOP_POINTS", "5").strip() or "5")

# فلتر اختياري: أقل FRP لعرض النقطة (0 = لا فلترة)
MIN_FRP = float(os.environ.get("FIRMS_MIN_FRP", "0").strip() or "0")


# ========= مدن مرجعية داخل السعودية (للـ "قرب المدينة") =========
# تقدر توسع القائمة مستقبلاً
CITIES = [
    ("الرياض", 24.7136, 46.6753),
    ("جدة", 21.4858, 39.1925),
    ("مكة", 21.3891, 39.8579),
    ("المدينة", 24.5247, 39.5692),
    ("الدمام", 26.4207, 50.0888),
    ("الجبيل", 27.0000, 49.6600),
    ("ينبع", 24.0895, 38.0618),
    ("تبوك", 28.3838, 36.5550),
    ("حائل", 27.5114, 41.7208),
    ("سكاكا", 29.9697, 40.2064),
    ("عرعر", 30.9753, 41.0381),
    ("جازان", 16.8892, 42.5706),
    ("أبها", 18.2164, 42.5053),
    ("نجران", 17.5650, 44.2289),
    ("الباحة", 20.0129, 41.4677),
    ("بريدة", 26.3592, 43.9818),
    ("القريات", 31.3315, 37.3428),
    ("العلا", 26.6085, 37.9232),
    ("نيوم", 29.3000, 35.0000),
]


def _haversine_km(lat1, lon1, lat2, lon2):
    # مسافة تقريبية بين نقطتين على الأرض
    R = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2) + math.cos(p1) * math.cos(p2) * (math.sin(dlon / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def _nearest_city(lat, lon):
    best = None
    for name, clat, clon in CITIES:
        d = _haversine_km(lat, lon, clat, clon)
        if best is None or d < best[1]:
            best = (name, d)
    return best  # (name, km)


def _firms_area_csv_url(map_key, source, bbox, day_range):
    # حسب وثائق FIRMS: /api/area/csv/[MAP_KEY]/[SOURCE]/[AREA_COORDINATES]/[DAY_RANGE]  [oai_citation:4‡firms.modaps.eosdis.nasa.gov](https://firms.modaps.eosdis.nasa.gov/api/area/)
    return f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{map_key}/{source}/{bbox}/{day_range}"


def _parse_dt(row):
    # FIRMS غالباً يعطي acq_date + acq_time (HHMM)
    d = (row.get("acq_date") or "").strip()
    t = (row.get("acq_time") or "").strip()
    if not d:
        return None
    if len(t) == 4 and t.isdigit():
        hh = int(t[:2])
        mm = int(t[2:])
        try:
            return datetime.datetime.fromisoformat(d).replace(hour=hh, minute=mm, tzinfo=datetime.timezone.utc)
        except Exception:
            return None
    try:
        return datetime.datetime.fromisoformat(d).replace(tzinfo=datetime.timezone.utc)
    except Exception:
        return None


def fetch_events():
    """
    يرجّع قائمة events بالشكل المتوقع في main.py/report_official.py:
    { "section": "fires", "title": "....", "meta": {...} }
    """
    if not FIRMS_MAP_KEY:
        return [{
            "section": "fires",
            "title": "⚠️ FIRMS: لا يوجد FIRMS_MAP_KEY في Secrets/Env"
        }]

    if DAY_RANGE < 1:
        day_range = 1
    elif DAY_RANGE > 5:
        day_range = 5
    else:
        day_range = DAY_RANGE

    url = _firms_area_csv_url(FIRMS_MAP_KEY, FIRMS_SOURCE, KSA_BBOX, day_range)
    try:
        r = requests.get(url, timeout=35)
        r.raise_for_status()
    except Exception as e:
        return [{
            "section": "fires",
            "title": f"⚠️ FIRMS: تعذر جلب البيانات ({e})"
        }]

    # قراءة CSV
    try:
        content = r.text
        reader = csv.DictReader(io.StringIO(content))
        rows = [row for row in reader]
    except Exception as e:
        return [{
            "section": "fires",
            "title": f"⚠️ FIRMS: فشل قراءة CSV ({e})"
        }]

    # فلترة FRP (اختياري)
    clean = []
    for row in rows:
        try:
            lat = float(row.get("latitude"))
            lon = float(row.get("longitude"))
        except Exception:
            continue

        frp = 0.0
        try:
            frp = float(row.get("frp") or 0)
        except Exception:
            frp = 0.0

        if frp < MIN_FRP:
            continue

        dt = _parse_dt(row)
        clean.append((frp, dt, lat, lon, row))

    if not clean:
        return [{
            "section": "fires",
            "title": "لا يوجد"
        }]

    # إحصاءات
    max_frp = max(x[0] for x in clean)
    last_dt = None
    for _, dt, *_ in clean:
        if dt and (last_dt is None or dt > last_dt):
            last_dt = dt

    # ترتيب أعلى نقاط FRP
    clean.sort(key=lambda x: (x[0], x[1] or datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)), reverse=True)
    top = clean[:max(1, TOP_POINTS)]

    events = []

    # الملخص
    last_str = last_dt.strftime("%Y-%m-%d %H%M UTC") if last_dt else "غير معروف"
    events.append({
        "section": "fires",
        "title": f"🔥 حرائق نشطة داخل السعودية — {len(clean)} رصد خلال آخر {day_range} يوم (أعلى FRP: {max_frp:.1f}) | آخر تحديث: {last_str}",
        "meta": {
            "count": len(clean),
            "max_frp": max_frp,
            "last_dt_utc": last_str,
            "source": FIRMS_SOURCE,
            "bbox": KSA_BBOX,
            "day_range": day_range
        }
    })

    # تفاصيل النقاط
    idx = 1
    for frp, dt, lat, lon, _ in top:
        near_name, near_km = _nearest_city(lat, lon)
        dt_str = dt.strftime("%Y-%m-%d %H%M UTC") if dt else "غير معروف"
        gmap = f"https://maps.google.com/?q={lat:.5f},{lon:.5f}"
        events.append({
            "section": "fires",
            "title": f"📍 نقطة #{idx}: قرب {near_name} (~{near_km:.0f} كم) | {lat:.5f},{lon:.5f} | FRP {frp:.1f} | {dt_str} | {gmap}",
            "meta": {
                "lat": lat,
                "lon": lon,
                "frp": frp,
                "dt_utc": dt_str,
                "near_city": near_name,
                "near_km": near_km,
                "gmap": gmap
            }
        })
        idx += 1

    return events
