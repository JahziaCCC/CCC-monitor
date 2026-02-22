import hashlib
import requests
from datetime import datetime, timedelta, timezone

# BBOX: السعودية + الجوار + البحر الأحمر/الخليج (قابل للتعديل)
BBOX = {"min_lat": 10.0, "max_lat": 38.0, "min_lon": 32.0, "max_lon": 61.0}

def _fp(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:24]

def _in_bbox(lat, lon):
    return (BBOX["min_lat"] <= lat <= BBOX["max_lat"]) and (BBOX["min_lon"] <= lon <= BBOX["max_lon"])

def fetch():
    todate = datetime.now(timezone.utc).date()
    fromdate = (todate - timedelta(days=7))

    url = (
        "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
        f"?eventlist=EQ;FL;TC;VO;DR"
        f"&fromdate={fromdate.isoformat()}&todate={todate.isoformat()}"
        f"&alertlevel=red;orange"
    )

    # ✅ مهم: لا تُسقط التشغيل إذا تأخر GDACS
    try:
        r = requests.get(url, timeout=40)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return []

    feats = data.get("features", [])

    items = []
    for f in feats:
        p = f.get("properties", {}) or {}
        geom = f.get("geometry", {}) or {}
        coords = (geom.get("coordinates") or [None, None])

        lon, lat = coords[0], coords[1]
        if lat is None or lon is None:
            continue

        if not _in_bbox(lat, lon):
            continue

        level = (p.get("alertlevel") or "").lower()
        name = p.get("name") or p.get("title") or "حدث"
        link = p.get("link") or p.get("url") or "https://new.gdacs.org"
        eventid = p.get("eventid", "")

        key = _fp(f"gdacs|{eventid}|{level}|{name}")

        items.append({
            "key": key,
            "section": "gdacs",
            "title": f"🌍 GDACS {level.upper()} — {name}",
            "link": link,
            "meta": {
                "lat": lat,
                "lon": lon,
                "level": level,
                "type": p.get("eventtype")
            }
        })

    return items
