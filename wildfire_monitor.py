# wildfire_monitor.py
import os
import io
import json
import math
import hashlib
import datetime
import requests
import csv
from typing import List, Dict, Any, Tuple

import matplotlib.pyplot as plt

# =========================
# إعدادات عامة
# =========================
BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
FIRMS_API_KEY = os.environ["FIRMS_API_KEY"]

STATE_FILE = "wildfire_state.json"

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))

# نطاق الرصد: السعودية + البحر الأحمر + الخليج العربي
REGION_BOX = (12.0, 34.5, 33.0, 57.5)

# فلترة متوازنة
BASE_MIN_CONF = 70
COAST_MIN_CONF = 80
COAST_MIN_FRP = 8.0

MAX_ALERTS = 25

# =========================
# أدوات جغرافيا
# =========================
def in_box(lat, lon, box):
    return box[0] <= lat <= box[1] and box[2] <= lon <= box[3]

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def maps_link(lat, lon):
    return f"https://maps.google.com/?q={lat:.5f},{lon:.5f}"

# =========================
# استبعاد حضري/صناعي
# =========================
URBAN_BOXES = [
    (24.2,25.2,46.1,47.2),
    (21.1,21.9,39.0,39.5),
    (26.2,26.6,50.0,50.4),
    (26.6,27.2,49.8,50.4),
    (24.4,24.7,39.5,39.8),
]

INDUSTRIAL_HOTSPOTS = [
    ("Ras Tanura",26.643,50.162,25),
    ("Jubail",27.012,49.650,30),
    ("Dammam Port",26.434,50.103,20),
    ("Yanbu",24.089,38.062,30),
    ("Jeddah Port",21.485,39.173,20),
]

RED_SEA_COAST_STRIP = (16.0,30.5,33.0,39.8)
GULF_COAST_STRIP = (24.0,29.5,47.5,56.5)

def in_urban(lat, lon):
    return any(in_box(lat, lon, b) for b in URBAN_BOXES)

def near_industrial(lat, lon):
    for _, hlat, hlon, rkm in INDUSTRIAL_HOTSPOTS:
        if haversine_km(lat, lon, hlat, hlon) <= rkm:
            return True
    return False

def is_probably_coastal(lat, lon):
    return in_box(lat, lon, RED_SEA_COAST_STRIP) or in_box(lat, lon, GULF_COAST_STRIP)

def is_wildfire_candidate(f):
    lat = float(f["latitude"])
    lon = float(f["longitude"])
    conf = float(f.get("confidence",0) or 0)
    frp = float(f.get("frp",0) or 0)

    if not in_box(lat, lon, REGION_BOX):
        return False

    if conf < BASE_MIN_CONF:
        return False

    if in_urban(lat, lon):
        return False

    if near_industrial(lat, lon):
        return False

    if is_probably_coastal(lat, lon):
        if frp < COAST_MIN_FRP:
            return False
        if conf < COAST_MIN_CONF:
            return False

    return True

# =========================
# Telegram
# =========================
def tg_send_message(text):
    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    requests.post(url, json={
        "chat_id": CHAT_ID,
        "text": text,
        "disable_web_page_preview": True
    }, timeout=30)

def tg_send_photo(png_bytes, caption=""):
    url = f"https://api.telegram.org/bot{BOT}/sendPhoto"
    files = {"photo": ("wildfires.png", png_bytes, "image/png")}
    data = {"chat_id": CHAT_ID, "caption": caption}
    requests.post(url, data=data, files=files, timeout=60)

# =========================
# State
# =========================
def load_state():
    if not os.path.exists(STATE_FILE):
        return {"seen":{}}
    try:
        with open(STATE_FILE,"r",encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"seen":{}}

def save_state(state):
    with open(STATE_FILE,"w",encoding="utf-8") as f:
        json.dump(state,f,ensure_ascii=False,indent=2)

def fire_id(f):
    s = f'{f["latitude"]},{f["longitude"]}|{f.get("acq_date","")}|{f.get("acq_time","")}'
    return hashlib.sha1(s.encode()).hexdigest()

# =========================
# NASA FIRMS
# =========================
def fetch_firms(source):
    min_lat,max_lat,min_lon,max_lon = REGION_BOX
    bbox = f"{min_lon},{min_lat},{max_lon},{max_lat}"
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{FIRMS_API_KEY}/{source}/{bbox}/2"

    r = requests.get(url, timeout=60)
    r.raise_for_status()

    reader = csv.DictReader(r.text.splitlines())
    rows = []
    for row in reader:
        rows.append(row)
    return rows

def normalize_fire(row, source):
    return {
        "latitude": float(row["latitude"]),
        "longitude": float(row["longitude"]),
        "acq_date": row.get("acq_date",""),
        "acq_time": row.get("acq_time",""),
        "confidence": float(row.get("confidence",0) or 0),
        "frp": float(row.get("frp",0) or 0),
        "satellite": row.get("satellite",source)
    }

# =========================
# رسم الخريطة
# =========================
def make_points_image(fires):
    lats = [f["latitude"] for f in fires]
    lons = [f["longitude"] for f in fires]

    fig = plt.figure(figsize=(7,7))
    ax = plt.gca()
    ax.grid(True)

    ax.scatter(lons,lats)

    for i,f in enumerate(fires,start=1):
        ax.text(f["longitude"],f["latitude"],f" {i}")

    buf = io.BytesIO()
    plt.tight_layout()
    fig.savefig(buf, format="png", dpi=170)
    plt.close(fig)
    return buf.getvalue()

# =========================
# إرسال التنبيه (C)
# =========================
def send_fire_alert_bundle(fires):
    now = datetime.datetime.now(KSA_TZ).strftime("%Y-%m-%d %H:%M KSA")

    fires = sorted(fires, key=lambda x:(x["confidence"],x["frp"]), reverse=True)[:MAX_ALERTS]

    png = make_points_image(fires)

    tg_send_photo(
        png,
        caption=f"🔥 خريطة الحرائق الطبيعية\n📍 السعودية + البحر الأحمر + الخليج\n🕒 {now}\n📊 العدد: {len(fires)}"
    )

    lines = [
        "🔥 تقرير الحرائق الطبيعية",
        f"📊 العدد: {len(fires)}",
        f"🕒 {now}",
        ""
    ]

    for i,f in enumerate(fires,start=1):
        lines.append(f"{i}) 🔥 FRP: {f['frp']} | ثقة: {f['confidence']}")
        lines.append(f"📍 {maps_link(f['latitude'],f['longitude'])}")
        lines.append("")

    tg_send_message("\n".join(lines))

# =========================
# MAIN
# =========================
def main():
    state = load_state()
    seen = state["seen"]

    sources = ["VIIRS_SNPP_NRT","VIIRS_NOAA20_NRT"]

    fires = []
    for s in sources:
        rows = fetch_firms(s)
        fires.extend([normalize_fire(r,s) for r in rows])

    filtered = [f for f in fires if is_wildfire_candidate(f)]

    new_fires = []
    for f in filtered:
        fid = fire_id(f)
        if fid in seen:
            continue
        new_fires.append(f)
        seen[fid] = True

    save_state(state)

    if new_fires:
        send_fire_alert_bundle(new_fires)
    else:
        tg_send_message("✅ لا توجد حرائق طبيعية جديدة حالياً.")

if __name__ == "__main__":
    main()
