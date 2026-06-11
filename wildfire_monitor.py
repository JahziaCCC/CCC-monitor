import os
import json
import math
import datetime
from typing import List, Tuple, Optional
import requests

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
FIRMS_KEY = os.environ["FIRMS_API_KEY"]

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
STATE_FILE = "wildfire_state.json"

# ========= السعودية فقط =========
BBOX = {
    "السعودية": (34.5, 16.0, 55.8, 32.6),
}

LOOKBACK_HOURS = 6
MIN_CONFIDENCE = "nominal"
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

def parse_dt_utc(date_str: str, time_str: str) -> Optional[datetime.datetime]:
    try:
        t = str(time_str).strip().zfill(4)
        hh = int(t[:2])
        mm = int(t[2:])
        if hh > 23 or mm > 59:
            return None
        return datetime.datetime.fromisoformat(date_str).replace(
            hour=hh, minute=mm, second=0, microsecond=0,
            tzinfo=datetime.timezone.utc
        )
    except Exception:
        return None

def within_hours(dt_utc: datetime.datetime, hours: int) -> bool:
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
    return dt_utc >= cutoff

def conf_bucket(c: str) -> str:
    c = str(c).lower().strip()
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

def pass_conf(min_conf: str, bucket: str) -> bool:
    if min_conf == "high":
        return bucket == "High"
    return bucket in ("High", "Nominal")

def is_natural_fire(row: dict) -> bool:
    t = row.get("type")
    if not t:
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

            # السعودية فقط
            if not (16.0 <= lat <= 32.6 and 34.5 <= lon <= 55.8):
                continue

            dt = parse_dt_utc(row.get("acq_date"), row.get("acq_time"))
            if not dt or not within_hours(dt, LOOKBACK_HOURS):
                continue

            try:
                frp = float(row["frp"]) if row.get("frp") else None
            except Exception:
                frp = None

            age = int((datetime.datetime.now(datetime.timezone.utc) - dt).total_seconds() // 60)

            events.append({
                "lat": lat,
                "lon": lon,
                "frp": frp,
                "conf": c,
                "age": age
            })

    count = len(events)
    delta = count - prev_count

    status = "🟢 طبيعي" if count == 0 else "🔴 تنبيه"

    trend = "↔ مستقر"
    if delta > 0:
        trend = f"↑ يتصاعد (+{delta})"
    elif delta < 0:
        trend = f"↓ يتحسن ({delta})"

    lines = [
        "🔥 رصد حرائق السعودية",
        f"🕒 {now_ksa_str()}",
        "",
        status,
        f"📊 العدد: {count}",
        f"📈 الاتجاه: {trend}",
        "",
    ]

    if events:
        top3 = sorted(events, key=lambda x: (x["frp"] or 0) * -1)[:3]

        lines.append("📌 أبرز النقاط:")
        for i, e in enumerate(top3, 1):
            frp = f"{e['frp']:.1f}" if e["frp"] else "—"
            lines.append(f"{i}) {e['lat']:.3f},{e['lon']:.3f} | FRP {frp} | {e['conf']} | {e['age']}m")

        lines.append("")
        lines.append("📍 الخريطة:")
        lines.append(google_maps(top3[0]["lat"], top3[0]["lon"]))

    lines.append("")
    lines.append("🗺️ FIRMS Map:")
    lines.append(map_link())

    tg_send("\n".join(lines))

    state["last_count"] = count
    state["last_update"] = now_ksa_str()
    save_state(state)

if __name__ == "__main__":
    main()
