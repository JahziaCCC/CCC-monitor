import os
import json
import math
import datetime
import requests
from typing import List, Dict, Tuple

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
FIRMS_KEY = os.environ["FIRMS_API_KEY"]

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
STATE_FILE = "wildfire_state.json"

# ========= السعودية فقط =========
BBOX = (34.5, 16.0, 55.8, 32.6)

SOURCES = [
    "VIIRS_SNPP_NRT",
    "VIIRS_NOAA20_NRT"
]

LOOKBACK_HOURS = 6
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/csv,*/*",
    "Connection": "close",
}

# =====================

def now_ksa():
    return datetime.datetime.now(KSA_TZ).strftime("%Y-%m-%d %H:%M KSA")

def load_state():
    if not os.path.exists(STATE_FILE):
        return {"seen": {}}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"seen": {}}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def tg_send(text):
    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    requests.post(url, json={
        "chat_id": CHAT_ID,
        "text": text,
        "disable_web_page_preview": True
    }, timeout=30)

def parse_csv(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) < 2:
        return []
    header = lines[0].split(",")
    out = []
    for line in lines[1:]:
        cols = line.split(",")
        if len(cols) == len(header):
            out.append({header[i]: cols[i] for i in range(len(header))})
    return out

# ========= فلتر السعودية الصارم =========
def is_saudi(lat, lon):
    return 16.0 <= lat <= 32.6 and 34.5 <= lon <= 55.8

def make_id(lat, lon, date, time):
    return f"{round(lat,2)}_{round(lon,2)}_{date}_{time}"

def main():

    state = load_state()
    seen = state.get("seen", {})

    min_lon, min_lat, max_lon, max_lat = BBOX
    bbox_str = f"{min_lon},{min_lat},{max_lon},{max_lat}"

    events = []

    for source in SOURCES:

        url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{FIRMS_KEY}/{source}/{bbox_str}/1"
        r = requests.get(url, headers=HTTP_HEADERS, timeout=60)

        if r.status_code != 200:
            continue

        rows = parse_csv(r.text)

        for row in rows:

            try:
                lat = float(row["latitude"])
                lon = float(row["longitude"])
            except:
                continue

            # 🔥 فلتر السعودية الصارم (أول شيء)
            if not is_saudi(lat, lon):
                continue

            date = row.get("acq_date")
            time = row.get("acq_time")

            if not date or not time:
                continue

            uid = make_id(lat, lon, date, time)

            if uid in seen:
                continue

            seen[uid] = True

            try:
                frp = float(row["frp"]) if row.get("frp") else None
            except:
                frp = None

            conf = row.get("confidence", "nominal")

            events.append({
                "lat": lat,
                "lon": lon,
                "frp": frp,
                "conf": conf,
                "date": date,
                "time": time
            })

    state["seen"] = seen
    save_state(state)

    if not events:
        return

    # ترتيب حسب القوة
    events.sort(key=lambda x: (x["frp"] or 0), reverse=True)
    top = events[:3]

    lines = []
    lines.append("🔥 رصد حرائق السعودية V3")
    lines.append(f"🕒 {now_ksa()}")
    lines.append("")
    lines.append(f"🚨 حرائق جديدة: {len(events)}")
    lines.append("")
    lines.append("📌 أبرز النقاط:")

    for i, e in enumerate(top, 1):
        frp = f"{e['frp']:.1f}" if e["frp"] else "—"
        lines.append(f"{i}) {e['lat']:.3f},{e['lon']:.3f} | FRP {frp} | {e['conf']}")

    lines.append("")
    lines.append(f"📍 https://www.google.com/maps?q={top[0]['lat']},{top[0]['lon']}")
    lines.append("🗺️ https://firms.modaps.eosdis.nasa.gov/map/")

    tg_send("\n".join(lines))

    state["last_run"] = now_ksa()
    save_state(state)


if __name__ == "__main__":
    main()
