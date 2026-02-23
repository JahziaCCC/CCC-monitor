# mon_fires.py
import os
import csv
import io
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

import requests

# مفتاح FIRMS (Secret)
FIRMS_MAP_KEY = os.environ.get("FIRMS_MAP_KEY", "").strip()

# للتشخيص في الـLogs (اختياري)
DEBUG_FIRMS = os.environ.get("DEBUG_FIRMS", "0").strip() == "1"

# نطاق السعودية (تقريبي وعملي للرصد)
# lon_min, lat_min, lon_max, lat_max
SAUDI_BBOX = os.environ.get("FIRMS_KSA_BBOX", "34.3,16.0,55.9,32.5")

# مصدر NRT (قابل للتغيير لاحقًا)
FIRMS_SOURCE = os.environ.get("FIRMS_SOURCE", "VIIRS_SNPP_NRT")

# يجلب آخر كم يوم من FIRMS (1 كافي غالبًا)
DAY_RANGE = int(os.environ.get("FIRMS_DAY_RANGE", "1"))

# نفلتر آخر كم ساعة “فعليًا” في التقرير
WINDOW_HOURS = int(os.environ.get("FIRMS_WINDOW_HOURS", "6"))


def _utcnow():
    return datetime.now(timezone.utc)


def _log(msg: str):
    if DEBUG_FIRMS:
        print(f"[FIRMS] {msg}")


def _parse_acq_datetime(acq_date: str, acq_time: str) -> datetime:
    """
    acq_date: YYYY-MM-DD
    acq_time: HHMM
    """
    acq_time = (acq_time or "").strip().zfill(4)
    hh = int(acq_time[:2])
    mm = int(acq_time[2:])
    y, m, d = [int(x) for x in acq_date.split("-")]
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


def fetch() -> List[Dict[str, Any]]:
    # 1) تأكد أن المفتاح موجود
    if not FIRMS_MAP_KEY:
        _log("FIRMS_MAP_KEY is missing -> returning []")
        return []

    # 2) endpoint الرسمي: area/csv/{MAP_KEY}/{SOURCE}/{BBOX}/{DAY_RANGE}
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{FIRMS_MAP_KEY}/{FIRMS_SOURCE}/{SAUDI_BBOX}/{DAY_RANGE}"
    _log(f"Requesting: source={FIRMS_SOURCE}, bbox={SAUDI_BBOX}, day_range={DAY_RANGE}, window_hours={WINDOW_HOURS}")

    try:
        r = requests.get(url, timeout=40)
    except Exception as e:
        _log(f"Request error: {e}")
        return []

    _log(f"HTTP {r.status_code}, response_len={len(r.text or '')}")

    if r.status_code != 200 or not (r.text or "").strip():
        # غالبًا مفتاح غير صحيح / rate limit / مشكلة مؤقتة
        _log("Non-200 or empty response -> returning []")
        return []

    # 3) Parse CSV
    f = io.StringIO(r.text)
    try:
        reader = csv.DictReader(f)
        rows = list(reader)
    except Exception as e:
        _log(f"CSV parse error: {e}")
        return []

    _log(f"CSV rows={len(rows)}")

    if not rows:
        return []

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
            lat, lon = 0.0, 0.0

        fires.append({"dt": dt, "lat": lat, "lon": lon, "frp": frp})

    _log(f"Filtered fires in last {WINDOW_HOURS}h: {len(fires)}")

    if not fires:
        return []

    count = len(fires)
    max_frp = max(x["frp"] for x in fires) if fires else 0.0
    top = max(fires, key=lambda x: x["frp"])

    title = f"🔥 حرائق نشطة داخل السعودية — {count} رصد خلال آخر {WINDOW_HOURS} ساعات (أعلى FRP: {max_frp:.1f})"

    return [{
        "section": "fires",
        "title": title,
        "meta": {
            "count": count,
            "max_frp": max_frp,
            "top_lat": top["lat"],
            "top_lon": top["lon"],
            "window_hours": WINDOW_HOURS,
            "source": FIRMS_SOURCE,
        }
    }]
