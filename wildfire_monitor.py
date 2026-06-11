import os
import json
import datetime
import requests

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
FIRMS_KEY = os.environ["FIRMS_API_KEY"]

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
STATE_FILE = "wildfire_state.json"

# ========= نطاق السعودية (متوازن) =========
BBOX = (34.5, 16.0, 55.2, 32.2)

SOURCES = [
    "VIIRS_SNPP_NRT",
    "VIIRS_NOAA20_NRT"
]

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
    requests.post(
        f"https://api.telegram.org/bot{BOT}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True},
        timeout=30
    )

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

# =========================================================
# 🔥 FLTER BALANCED (مهم: يمنع الخليج بدون تشدد زائد)
# =========================================================

def is_saudi(lat, lon):

    if not (16.0 <= lat <= 32.2):
        return False
    if not (34.5 <= lon <= 55.2):
        return False

    # ❌ الخليج
    if lat < 27.0 and lon > 50.5:
        return False

    # ❌ شرق عمان
    if lat < 23.0 and lon > 56.0:
        return False

    return True

# =========================================================

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

        try:
            r = requests.get(url, headers=HTTP_HEADERS, timeout=60)
        except:
            continue

        if r.status_code != 200:
            continue

        rows = parse_csv(r.text)

        for row in rows:

            try:
                lat = float(row["latitude"])
                lon = float(row["longitude"])
            except:
                continue

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
                frp = float(row["frp"]) if row.get("frp") else 0
            except:
                frp = 0

            # 🔥 فلتر خفيف مهم
            if frp < 5:
                continue

            events.append({
                "lat": lat,
                "lon": lon,
                "frp": frp,
                "conf": row.get("confidence", "nominal")
            })

    state["seen"] = seen
    save_state(state)

    # =========================
    # 📢 رسائل عربية واضحة
    # =========================

    if not events:
        tg_send(f"""🟢 لا توجد حرائق حالياً داخل السعودية

🕒 {now_ksa()}
🛰️ النظام يعمل بشكل طبيعي""")
        return

    events.sort(key=lambda x: x["frp"], reverse=True)
    top = events[:3]

    msg = []
    msg.append("🔥 رصد حرائق السعودية - V4 Balanced")
    msg.append(f"🕒 {now_ksa()}")
    msg.append("")
    msg.append(f"🚨 تم رصد {len(events)} حريق / نقطة حرارية")
    msg.append("")
    msg.append("📌 أبرز المواقع:")

    for i, e in enumerate(top, 1):
        msg.append(
            f"{i}) الموقع: {e['lat']:.3f}, {e['lon']:.3f}\n"
            f"   🔥 قوة الحريق (FRP): {e['frp']:.1f}\n"
            f"   📊 الحالة: {e['conf']}"
        )

    msg.append("")
    msg.append(f"📍 الخريطة: https://www.google.com/maps?q={top[0]['lat']},{top[0]['lon']}")
    msg.append("🗺️ FIRMS: https://firms.modaps.eosdis.nasa.gov/map/")

    tg_send("\n".join(msg))


if __name__ == "__main__":
    main()
