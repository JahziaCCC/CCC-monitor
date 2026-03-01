import os
import json
import math
import datetime
from typing import Dict, List, Tuple, Optional
import requests

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
FIRMS_KEY = os.environ["FIRMS_API_KEY"]

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
STATE_FILE = "wildfire_state.json"

# ========= مناطق الرصد =========
BBOX = {
    "السعودية": (34.5, 16.0, 55.8, 32.6),
    "البحر الأحمر": (32.0, 12.0, 44.5, 30.5),
    "الخليج العربي": (47.0, 22.0, 56.8, 30.8),
}

LOOKBACK_HOURS = 6
MIN_CONFIDENCE = "nominal"   # nominal أو high
MAX_POINTS_PER_REGION = 300

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/csv,*/*",
    "Connection": "close",
}

def firms_url_for_bbox(bbox: Tuple[float, float, float, float], hours: int) -> str:
    min_lon, min_lat, max_lon, max_lat = bbox
    days = max(1, math.ceil(hours / 24))
    bbox_str = f"{min_lon},{min_lat},{max_lon},{max_lat}"
    source = "VIIRS_SNPP_NRT"
    return f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{FIRMS_KEY}/{source}/{bbox_str}/{days}"

def now_ksa_str() -> str:
    return datetime.datetime.now(KSA_TZ).strftime("%Y-%m-%d %H:%M KSA")

def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_state(s: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)

def tg_send(text: str) -> None:
    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    requests.post(
        url,
        json={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True},
        timeout=30
    ).raise_for_status()

def parse_csv(text: str) -> List[dict]:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) < 2:
        return []
    header = lines[0].split(",")
    out = []
    for ln in lines[1:]:
        cols = ln.split(",")
        if len(cols) != len(header):
            continue
        out.append({header[i]: cols[i] for i in range(len(header))})
    return out

# ===== FIX وقت FIRMS =====
def parse_dt_utc(date_str: str, time_str: str) -> Optional[datetime.datetime]:
    try:
        t = str(time_str).strip().zfill(4)
        hh = int(t[:2])
        mm = int(t[2:])
        if hh > 23 or mm > 59:
            return None
        return datetime.datetime.fromisoformat(date_str).replace(
            hour=hh, minute=mm, second=0, microsecond=0, tzinfo=datetime.timezone.utc
        )
    except Exception:
        return None

def within_hours(dt_utc: datetime.datetime, hours: int) -> bool:
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
    return dt_utc >= cutoff

def conf_bucket(c: str) -> str:
    c = str(c).strip().lower()
    if c in ("h", "high"):
        return "High"
    if c in ("n", "nominal"):
        return "Nominal"
    if c in ("l", "low"):
        return "Low"
    try:
        v = float(c)
        if v >= 80:
            return "High"
        if v >= 30:
            return "Nominal"
        return "Low"
    except Exception:
        return "Nominal"

def pass_conf(min_conf: str, bucketed: str) -> bool:
    if min_conf.lower().strip() == "high":
        return bucketed == "High"
    return bucketed in ("High", "Nominal")

def is_natural_fire(row: dict) -> bool:
    """
    VIIRS 'type':
      0 = presumed vegetation fire  ✅ نعتبرها حرائق طبيعية
      1 = active volcano
      2 = other static land source (غالباً صناعي ثابت / gas flares)
    """
    t = row.get("type")
    if t is None or t == "":
        return True
    try:
        return int(float(t)) == 0
    except Exception:
        return True

def map_link() -> str:
    return "https://firms.modaps.eosdis.nasa.gov/map/"

def google_maps(lat: float, lon: float) -> str:
    return f"https://www.google.com/maps?q={lat},{lon}"

def main():
    state = load_state()
    prev_count = int(state.get("last_count", 0))

    events: List[dict] = []

    for scope, bbox in BBOX.items():
        url = firms_url_for_bbox(bbox, LOOKBACK_HOURS)
        r = requests.get(url, headers=HTTP_HEADERS, timeout=60)
        if r.status_code != 200:
            continue

        rows = parse_csv(r.text)[:MAX_POINTS_PER_REGION]

        for row in rows:
            acq_date = row.get("acq_date")
            acq_time = row.get("acq_time")
            if not acq_date or not acq_time:
                continue

            dt = parse_dt_utc(acq_date, acq_time)
            if dt is None:
                continue

            if not within_hours(dt, LOOKBACK_HOURS):
                continue

            if not is_natural_fire(row):
                continue

            c = conf_bucket(row.get("confidence", ""))
            if not pass_conf(MIN_CONFIDENCE, c):
                continue

            try:
                lat = float(row["latitude"])
                lon = float(row["longitude"])
            except Exception:
                continue

            frp = None
            try:
                frp = float(row.get("frp")) if row.get("frp") not in (None, "") else None
            except Exception:
                frp = None

            age = int((datetime.datetime.now(datetime.timezone.utc) - dt).total_seconds() // 60)

            events.append({
                "scope": scope,
                "lat": lat,
                "lon": lon,
                "frp": frp,
                "conf": c,
                "age": age
            })

    count = len(events)
    delta = count - prev_count

    status = "🟢 حالة الرصد: طبيعي" if count == 0 else "🔴 حالة الرصد: تنبيه"

    if delta > 0:
        trend = f"↑ يتصاعد (+{delta})"
    elif delta < 0:
        trend = f"↓ يتحسن ({delta})"
    else:
        trend = "↔ مستقر (+0)"

    lines: List[str] = []
    lines.append("🔥 رصد حرائق طبيعية")
    lines.append(f"🕒 {now_ksa_str()}")
    lines.append("")
    lines.append(status)
    lines.append(f"📊 عدد الحرائق: {count}")
    lines.append(f"📈 اتجاه الحالة: {trend}")
    lines.append("🛰️ المصدر: NASA FIRMS (VIIRS)")
    lines.append("🧪 فلترة: حرائق طبيعية")
    lines.append("")

    if count > 0:
        # Top 3 by FRP desc then newest
        def key_event(e):
            frp_val = e["frp"] if e["frp"] is not None else -1.0
            return (-frp_val, e["age"])
        top3 = sorted(events, key=key_event)[:3]

        lines.append("📌 أبرز النقاط:")
        for i, e in enumerate(top3, start=1):
            frp_txt = f"{e['frp']:.1f}" if e["frp"] is not None else "—"
            lines.append(f"{i}) {e['lat']:.3f},{e['lon']:.3f} | FRP {frp_txt} | {e['conf']} | {e['age']}m")

        lines.append("")
        lines.append("📍 رابط Google Maps (أبرز نقطة):")
        lines.append(google_maps(top3[0]["lat"], top3[0]["lon"]))
        lines.append("")
        lines.append("🗺️ روابط Google Maps (أفضل 3):")
        for i, e in enumerate(top3, start=1):
            lines.append(f"{i}) {google_maps(e['lat'], e['lon'])}")
        lines.append("")

    lines.append(f"🔗 عرض الخريطة: {map_link()}")

    tg_send("\n".join(lines))

    state["last_count"] = count
    state["last_update"] = now_ksa_str()
    save_state(state)

if __name__ == "__main__":
    main()
