# mon_fires.py
import os
import csv
import io
import math
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Tuple

import requests

# ===== Secrets / Env =====
FIRMS_MAP_KEY = os.environ.get("FIRMS_MAP_KEY", "").strip()
DEBUG_FIRMS = os.environ.get("DEBUG_FIRMS", "0").strip() == "1"

# FIRMS NRT source
FIRMS_SOURCE = os.environ.get("FIRMS_SOURCE", "VIIRS_SNPP_NRT")

# Time window for "active" fires
WINDOW_HOURS = int(os.environ.get("FIRMS_WINDOW_HOURS", "24"))

# API day range (1 is usually enough)
DAY_RANGE = int(os.environ.get("FIRMS_DAY_RANGE", "1"))

# Saudi bbox (approx) lon_min,lat_min,lon_max,lat_max
KSA_BBOX_BASE = (34.3, 16.0, 55.9, 32.5)

# buffer around borders to catch near-border events
BORDER_BUFFER_DEG = float(os.environ.get("FIRMS_BORDER_BUFFER_DEG", "1.2"))

# Smart alert radius around each region reference point
ALERT_RADIUS_KM = float(os.environ.get("FIRMS_ALERT_RADIUS_KM", "120"))


def _log(msg: str):
    if DEBUG_FIRMS:
        print(f"[FIRMS] {msg}")


def _utcnow():
    return datetime.now(timezone.utc)


def _bbox_with_buffer(b: Tuple[float, float, float, float], buf: float) -> Tuple[float, float, float, float]:
    lon_min, lat_min, lon_max, lat_max = b
    return (lon_min - buf, lat_min - buf, lon_max + buf, lat_max + buf)


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _parse_acq_datetime(acq_date: str, acq_time: str) -> datetime:
    # acq_date: YYYY-MM-DD , acq_time: HHMM
    acq_time = (acq_time or "").strip().zfill(4)
    hh = int(acq_time[:2])
    mm = int(acq_time[2:])
    y, m, d = [int(x) for x in acq_date.split("-")]
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


# ===== 13 Regions + NEOM + AlUla (reference points) =====
# ملاحظة: هذه نقاط مرجعية (مراكز/عواصم مناطق) للتقريب التشغيلي.
REGION_POINTS = [
    ("الرياض", 24.7136, 46.6753),
    ("مكة المكرمة", 21.3891, 39.8579),
    ("المدينة المنورة", 24.5247, 39.5692),
    ("المنطقة الشرقية (الدمام)", 26.4207, 50.0888),
    ("القصيم (بريدة)", 26.3592, 43.9818),
    ("عسير (أبها)", 18.2164, 42.5053),
    ("تبوك", 28.3838, 36.5662),
    ("حائل", 27.5114, 41.7208),
    ("الحدود الشمالية (عرعر)", 30.9753, 41.0381),
    ("جازان", 16.8892, 42.5706),
    ("نجران", 17.4924, 44.1277),
    ("الباحة", 20.0129, 41.4677),
    ("الجوف (سكاكا)", 29.9697, 40.2064),

    # إضافات طلبتها
    ("نيوم", 28.0000, 35.0000),
    ("العلا", 26.6083, 37.9232),
]


def _nearest_region(lat: float, lon: float) -> Tuple[str, float]:
    best_name = "غير محدد"
    best_km = 1e9
    for name, rlat, rlon in REGION_POINTS:
        km = _haversine_km(lat, lon, rlat, rlon)
        if km < best_km:
            best_km = km
            best_name = name
    return best_name, best_km


def fetch() -> List[Dict[str, Any]]:
    if not FIRMS_MAP_KEY:
        _log("FIRMS_MAP_KEY missing -> []")
        return []

    bbox = _bbox_with_buffer(KSA_BBOX_BASE, BORDER_BUFFER_DEG)
    bbox_str = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{FIRMS_MAP_KEY}/{FIRMS_SOURCE}/{bbox_str}/{DAY_RANGE}"

    _log(f"Requesting FIRMS: source={FIRMS_SOURCE}, bbox={bbox_str}, day_range={DAY_RANGE}, window={WINDOW_HOURS}h")

    try:
        r = requests.get(url, timeout=45)
    except Exception as e:
        _log(f"Request error: {e}")
        return []

    _log(f"HTTP {r.status_code}, len={len(r.text or '')}")

    if r.status_code != 200 or not (r.text or "").strip():
        # ما نوقف التشغيل — فقط نرجع فاضي
        return []

    # Parse CSV
    try:
        reader = csv.DictReader(io.StringIO(r.text))
        rows = list(reader)
    except Exception as e:
        _log(f"CSV parse error: {e}")
        return []

    if not rows:
        # إثبات فحص (أفضل تشغيلياً)
        return [{
            "section": "fires",
            "title": f"🔥 لا توجد حرائق نشطة داخل نطاق المملكة (±{BORDER_BUFFER_DEG}° حدود) خلال آخر {WINDOW_HOURS} ساعة (تم الفحص).",
            "meta": {"count": 0, "window_hours": WINDOW_HOURS, "source": FIRMS_SOURCE}
        }]

    now = _utcnow()
    window_start = now - timedelta(hours=WINDOW_HOURS)

    fires = []
    for row in rows:
        try:
            dt = _parse_acq_datetime(row.get("acq_date", ""), row.get("acq_time", "0"))
        except Exception:
            continue

        if dt < window_start:
            continue

        try:
            lat = float(row.get("latitude", "0") or 0)
            lon = float(row.get("longitude", "0") or 0)
        except Exception:
            continue

        try:
            frp = float(row.get("frp", "0") or 0)
        except Exception:
            frp = 0.0

        fires.append((dt, lat, lon, frp))

    _log(f"Filtered fires in last {WINDOW_HOURS}h: {len(fires)}")

    if not fires:
        return [{
            "section": "fires",
            "title": f"🔥 لا توجد حرائق نشطة داخل نطاق المملكة (±{BORDER_BUFFER_DEG}° حدود) خلال آخر {WINDOW_HOURS} ساعة (تم الفحص).",
            "meta": {"count": 0, "window_hours": WINDOW_HOURS, "source": FIRMS_SOURCE}
        }]

    count = len(fires)
    max_frp = max(x[3] for x in fires)
    top = max(fires, key=lambda x: x[3])  # أعلى FRP
    top_dt, top_lat, top_lon, top_frp = top

    nearest_name, nearest_km = _nearest_region(top_lat, top_lon)

    # Smart alert: إذا أقرب منطقة ضمن ALERT_RADIUS_KM نرفع تنبيه
    if nearest_km <= ALERT_RADIUS_KM:
        alert_tag = "🚨 تنبيه قريب من منطقة"
    else:
        alert_tag = "📍 أقرب منطقة"

    title = (
        f"🔥 حرائق نشطة داخل/حول المملكة — {count} رصد خلال آخر {WINDOW_HOURS} ساعة "
        f"(أعلى FRP: {max_frp:.1f}) | {alert_tag}: {nearest_name} (~{nearest_km:.0f} كم) "
        f"| أعلى نقطة: {top_lat:.2f},{top_lon:.2f} | {top_dt.strftime('%Y-%m-%d %H:%M UTC')}"
    )

    return [{
        "section": "fires",
        "title": title,
        "meta": {
            "count": count,
            "max_frp": max_frp,
            "top_lat": top_lat,
            "top_lon": top_lon,
            "top_frp": top_frp,
            "nearest_region": nearest_name,
            "nearest_km": nearest_km,
            "alert_radius_km": ALERT_RADIUS_KM,
            "window_hours": WINDOW_HOURS,
            "source": FIRMS_SOURCE,
            "bbox": bbox_str,
        }
    }]
