# mon_fires.py
import os
import csv
import io
import math
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Tuple

import requests

# ======= إعدادات =======
FIRMS_MAP_KEY = os.environ.get("FIRMS_MAP_KEY", "").strip()
DEBUG_FIRMS = os.environ.get("DEBUG_FIRMS", "0").strip() == "1"

# مصدر FIRMS (NRT)
FIRMS_SOURCE = os.environ.get("FIRMS_SOURCE", "VIIRS_SNPP_NRT")

# آخر كم ساعة نعتبرها "نشطة" للتقرير (أفضل تشغيلياً 24 ساعة)
WINDOW_HOURS = int(os.environ.get("FIRMS_WINDOW_HOURS", "24"))

# آخر كم يوم من FIRMS نطلب (1 كافي عادة)
DAY_RANGE = int(os.environ.get("FIRMS_DAY_RANGE", "1"))

# نطاق السعودية (تقريبي) lon_min,lat_min,lon_max,lat_max
KSA_BBOX_BASE = (34.3, 16.0, 55.9, 32.5)

# هامش للحدود (درجة) للتوسعة — 1.0 يعني تقريباً ~110km latitude
BORDER_BUFFER_DEG = float(os.environ.get("FIRMS_BORDER_BUFFER_DEG", "1.2"))


# ======= قائمة مرجعية (13 منطقة + نيوم + العلا) لتحديد أقرب نقطة =======
# (تقدر تزودها لاحقاً)
REF_POINTS = [
    ("الرياض", 24.7136, 46.6753),
    ("جدة", 21.4858, 39.1925),
    ("مكة", 21.3891, 39.8579),
    ("المدينة", 24.5247, 39.5692),
    ("الدمام", 26.4207, 50.0888),
    ("تبوك", 28.3838, 36.5662),
    ("أبها", 18.2164, 42.5053),
    ("جازان", 16.8892, 42.5706),
    ("نجران", 17.4924, 44.1277),
    ("حائل", 27.5114, 41.7208),
    ("القصيم (بريدة)", 26.3592, 43.9818),
    ("الجوف (سكاكا)", 29.9697, 40.2064),
    ("الحدود الشمالية (عرعر)", 30.9753, 41.0381),
    ("القريات", 31.3317, 37.3428),
    ("نيوم", 28.0000, 35.0000),
    ("العلا", 26.6083, 37.9232),
]


def _log(msg: str):
    if DEBUG_FIRMS:
        print(f"[FIRMS] {msg}")


def _utcnow():
    return datetime.now(timezone.utc)


def _bbox_with_buffer(b: Tuple[float, float, float, float], buf: float) -> Tuple[float, float, float, float]:
    lon_min, lat_min, lon_max, lat_max = b
    return (
        lon_min - buf,
        lat_min - buf,
        lon_max + buf,
        lat_max + buf,
    )


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    # مسافة تقريبية بالكيلومتر
    R = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _nearest_ref(lat: float, lon: float) -> Tuple[str, float]:
    best_name = "غير محدد"
    best_km = 1e9
    for name, rlat, rlon in REF_POINTS:
        km = _haversine_km(lat, lon, rlat, rlon)
        if km < best_km:
            best_km = km
            best_name = name
    return best_name, best_km


def _parse_acq_datetime(acq_date: str, acq_time: str) -> datetime:
    # acq_date: YYYY-MM-DD , acq_time: HHMM
    acq_time = (acq_time or "").strip().zfill(4)
    hh = int(acq_time[:2])
    mm = int(acq_time[2:])
    y, m, d = [int(x) for x in acq_date.split("-")]
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


def fetch() -> List[Dict[str, Any]]:
    # 1) تحقق من المفتاح
    if not FIRMS_MAP_KEY:
        _log("FIRMS_MAP_KEY missing -> []")
        return []

    # 2) وسّع نطاق السعودية بهامش حدود
    bbox = _bbox_with_buffer(KSA_BBOX_BASE, BORDER_BUFFER_DEG)
    bbox_str = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"

    # 3) نداء FIRMS
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{FIRMS_MAP_KEY}/{FIRMS_SOURCE}/{bbox_str}/{DAY_RANGE}"
    _log(f"Request: {url}")

    try:
        r = requests.get(url, timeout=45)
    except Exception as e:
        _log(f"Request error: {e}")
        return []

    _log(f"HTTP {r.status_code}, len={len(r.text or '')}")

    if r.status_code != 200 or not (r.text or "").strip():
        return []

    # 4) Parse CSV
    try:
        reader = csv.DictReader(io.StringIO(r.text))
        rows = list(reader)
    except Exception as e:
        _log(f"CSV parse error: {e}")
        return []

    _log(f"CSV rows={len(rows)}")

    if not rows:
        # نرجّع "لا يوجد" بشكل صريح (أفضل تشغيلياً)
        return [{
            "section": "fires",
            "title": f"🔥 لا توجد حرائق نشطة داخل نطاق المملكة (±{BORDER_BUFFER_DEG}° حدود) خلال آخر {WINDOW_HOURS} ساعة.",
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
            frp = float(row.get("frp", "0") or 0)
        except Exception:
            frp = 0.0

        try:
            lat = float(row.get("latitude", "0") or 0)
            lon = float(row.get("longitude", "0") or 0)
        except Exception:
            continue

        fires.append((dt, lat, lon, frp))

    _log(f"Filtered fires in {WINDOW_HOURS}h: {len(fires)}")

    if not fires:
        return [{
            "section": "fires",
            "title": f"🔥 لا توجد حرائق نشطة داخل نطاق المملكة (±{BORDER_BUFFER_DEG}° حدود) خلال آخر {WINDOW_HOURS} ساعة.",
            "meta": {"count": 0, "window_hours": WINDOW_HOURS, "source": FIRMS_SOURCE}
        }]

    # 5) تلخيص
    count = len(fires)
    max_frp = max(x[3] for x in fires)
    top = max(fires, key=lambda x: x[3])  # أعلى FRP
    top_dt, top_lat, top_lon, top_frp = top

    nearest_name, nearest_km = _nearest_ref(top_lat, top_lon)

    title = (
        f"🔥 حرائق نشطة داخل/حول المملكة — {count} رصد خلال آخر {WINDOW_HOURS} ساعة "
        f"(أعلى FRP: {max_frp:.1f})"
    )

    # سطر إضافي داخل نفس العنوان (بدون تغيير شكل التقرير)
    # ملاحظة: report_official يضع "- {title}" فقط، فنجعلها جملة واحدة واضحة.
    detail = (
        f" | أقرب منطقة: {nearest_name} (~{nearest_km:.0f} كم) "
        f"| أعلى نقطة: {top_lat:.2f},{top_lon:.2f} | {top_dt.strftime('%Y-%m-%d %H:%M UTC')}"
    )

    return [{
        "section": "fires",
        "title": title + detail,
        "meta": {
            "count": count,
            "max_frp": max_frp,
            "top_lat": top_lat,
            "top_lon": top_lon,
            "top_frp": top_frp,
            "nearest": nearest_name,
            "nearest_km": nearest_km,
            "window_hours": WINDOW_HOURS,
            "source": FIRMS_SOURCE,
            "bbox": bbox_str,
        }
    }]
