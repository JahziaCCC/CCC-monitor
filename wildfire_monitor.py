import os
import json
import math
import datetime
import requests

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
FIRMS_KEY = os.environ["FIRMS_API_KEY"]

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
STATE_FILE = "wildfire_state.json"

BBOX = (34.8, 16.5, 55.3, 31.8)

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

def tg_send(text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True},
            timeout=30
        )
    except Exception as e:
        print("Telegram error:", e)

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

def is_saudi(lat, lon):
    return 16.5 <= lat <= 32.0 and 34.8 <= lon <= 55.3

def make_id(lat, lon, date, time):
    return f"{round(lat,2)}_{round(lon,2)}_{date}_{time}"

def main():

    min_lon, min_lat, max_lon, max_lat = BBOX
    bbox_str = f"{min_lon},{min_lat},{max_lon},{max_lat}"

    seen = set()
    events = []

    debug_total_rows = 0
    debug_outside_saudi = 0
    debug_duplicate = 0

    for source in SOURCES:

        url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{FIRMS_KEY}/{source}/{bbox_str}/1"

        try:
            r = requests.get(url, headers=HTTP_HEADERS, timeout=60)
        except Exception as e:
            tg_send(f"❌ API error: {e}")
            return

        if r.status_code != 200:
            tg_send(f"❌ HTTP error: {r.status_code}")
            return

        rows = parse_csv(r.text)
        debug_total_rows += len(rows)

        for row in rows:

            try:
                lat = float(row["latitude"])
                lon = float(row["longitude"])
            except:
                continue

            if not is_saudi(lat, lon):
                debug_outside_saudi += 1
                continue

            date = row.get("acq_date")
            time = row.get("acq_time")

            if not date or not time:
                continue

            uid = make_id(lat, lon, date, time)

            if uid in seen:
                debug_duplicate += 1
                continue

            seen.add(uid)

            try:
                frp = float(row["frp"]) if row.get("frp") else None
            except:
                frp = None

            events.append({
                "lat": lat,
                "lon": lon,
                "frp": frp,
                "conf": row.get("confidence", "nominal")
            })

    # ================= DEBUG REPORT =================

    msg = []
    msg.append("🔥 V4 DEBUG REPORT - Saudi Fire Monitor")
    msg.append(f"🕒 {now_ksa()}")
    msg.append("")
    msg.append(f"📊 Total rows from FIRMS: {debug_total_rows}")
    msg.append(f"🚫 Outside Saudi filter: {debug_outside_saudi}")
    msg.append(f"🔁 Duplicates removed: {debug_duplicate}")
    msg.append(f"📌 Final events: {len(events)}")
    msg.append("")

    if len(events) == 0:
        msg.append("❌ السبب المحتمل لعدم وصول تنبيه:")
        if debug_total_rows == 0:
            msg.append("- لا توجد بيانات من API (مشكلة اتصال أو key)")
        elif debug_outside_saudi > debug_total_rows * 0.8:
            msg.append("- أغلب البيانات خارج السعودية (فلتر صارم جدًا)")
        elif debug_duplicate > 0:
            msg.append("- كل الأحداث مكررة (تم إرسالها سابقًا)")
        else:
            msg.append("- لا توجد حرائق فعلية في المنطقة حالياً")

        msg.append("")
        msg.append("🗺️ FIRMS Map:")
        msg.append("https://firms.modaps.eosdis.nasa.gov/map/")

        tg_send("\n".join(msg))
        return

    # ترتيب
    events.sort(key=lambda x: (x["frp"] or 0), reverse=True)
    top = events[:3]

    msg.append("🚨 حرائق مكتشفة:")
    msg.append(f"عدد: {len(events)}")
    msg.append("")
    msg.append("📌 أبرز النقاط:")

    for i, e in enumerate(top, 1):
        frp = f"{e['frp']:.1f}" if e["frp"] else "—"
        msg.append(f"{i}) {e['lat']:.3f},{e['lon']:.3f} | FRP {frp} | {e['conf']}")

    msg.append("")
    msg.append(f"📍 https://www.google.com/maps?q={top[0]['lat']},{top[0]['lon']}")
    msg.append("🗺️ https://firms.modaps.eosdis.nasa.gov/map/")

    tg_send("\n".join(msg))


if __name__ == "__main__":
    main()
