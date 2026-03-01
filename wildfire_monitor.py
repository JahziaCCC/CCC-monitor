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

def now_ksa_str():
    return datetime.datetime.now(KSA_TZ).strftime("%Y-%m-%d %H:%M KSA")

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_state(s):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)

def tg_send(text):
    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    requests.post(
        url,
        json={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True},
        timeout=30
    ).raise_for_status()

def parse_csv(text):
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
def parse_dt_utc(date_str, time_str):
    try:
        t = str(time_str).strip().zfill(4)
        hh = int(t[:2])
        mm = int(t[2:])
        if hh > 23 or mm > 59:
            return None
        return datetime.datetime.fromisoformat(date_str).replace(
            hour=hh,
            minute=mm,
            tzinfo=datetime.timezone.utc
        )
    except:
        return None

def within_hours(dt_utc, hours):
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
    return dt_utc >= cutoff

def conf_bucket(c):
    c = str(c).lower()
    if c in ["h", "high"]:
        return "High"
    if c in ["n", "nominal"]:
        return "Nominal"
    return "Low"

def pass_conf(min_conf, c):
    if min_conf == "high":
        return c == "High"
    return c in ["High", "Nominal"]

def is_natural_fire(row):
    t = row.get("type")
    if not t:
        return True
    try:
        return int(float(t)) == 0
    except:
        return True

def map_link():
    return "https://firms.modaps.eosdis.nasa.gov/map/"

def google_map(lat, lon):
    return f"https://www.google.com/maps?q={lat},{lon}"

def main():

    state = load_state()
    prev_count = int(state.get("last_count", 0))

    events = []
    per_scope = {k: 0 for k in BBOX}

    for scope, bbox in BBOX.items():

        r = requests.get(
            firms_url_for_bbox(bbox, LOOKBACK_HOURS),
            headers=HTTP_HEADERS,
            timeout=60
        )

        if r.status_code != 200:
            continue

        rows = parse_csv(r.text)[:MAX_POINTS_PER_REGION]

        for row in rows:

            dt = parse_dt_utc(row.get("acq_date"), row.get("acq_time"))
            if dt is None:
                continue

            if not within_hours(dt, LOOKBACK_HOURS):
                continue

            if not is_natural_fire(row):
                continue

            c = conf_bucket(row.get("confidence"))
            if not pass_conf(MIN_CONFIDENCE, c):
                continue

            try:
                lat = float(row["latitude"])
                lon = float(row["longitude"])
            except:
                continue

            frp = None
            try:
                frp = float(row.get("frp"))
            except:
                pass

            age = int((datetime.datetime.now(datetime.timezone.utc)-dt).total_seconds()/60)

            events.append({
                "scope": scope,
                "lat": lat,
                "lon": lon,
                "frp": frp,
                "conf": c,
                "age": age
            })

            per_scope[scope] += 1

    count = len(events)
    delta = count - prev_count

    status = "🟢 حالة الرصد: طبيعي" if count == 0 else "🔴 حالة الرصد: تنبيه"

    if delta > 0:
        trend = f"↑ يتصاعد (+{delta})"
    elif delta < 0:
        trend = f"↓ يتحسن ({delta})"
    else:
        trend = "↔ مستقر (+0)"

    lines = []
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

        top3 = sorted(events, key=lambda x: -(x["frp"] or 0))[:3]

        lines.append("📌 أبرز النقاط:")
        for i,e in enumerate(top3,1):
            frp = f"{e['frp']:.1f}" if e["frp"] else "—"
            lines.append(f"{i}) {e['lat']:.3f},{e['lon']:.3f} | FRP {frp} | {e['conf']} | {e['age']}m")

        lines.append("")
        lines.append("📍 استعراض الموقع:")
        lines.append(google_map(top3[0]["lat"], top3[0]["lon"]))
        lines.append("")

    lines.append(f"🔗 عرض الخريطة: {map_link()}")

    tg_send("\n".join(lines))

    state["last_count"] = count
    state["last_update"] = now_ksa_str()
    save_state(state)

if __name__ == "__main__":
    main()
