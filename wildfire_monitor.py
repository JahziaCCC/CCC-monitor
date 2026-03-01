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

# ========= مناطق الرصد (Bounding Boxes) =========
# bbox format: (min_lon, min_lat, max_lon, max_lat)
BBOX = {
    "السعودية": (34.5, 16.0, 55.8, 32.6),
    "البحر الأحمر": (32.0, 12.0, 44.5, 30.5),
    "الخليج العربي": (47.0, 22.0, 56.8, 30.8),
}

# ========= إعدادات رصد =========
LOOKBACK_HOURS = 6          # أحدث 6 ساعات
MIN_CONFIDENCE = "nominal"  # nominal أو high
MAX_POINTS_PER_REGION = 300 # حماية

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0 Safari/537.36",
    "Accept": "text/csv,application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
    "Connection": "close",
}

def firms_url_for_bbox(bbox: Tuple[float, float, float, float], hours: int) -> str:
    """
    FIRMS API area CSV:
    /api/area/csv/{key}/{source}/{bbox}/{days}
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    days = max(1, math.ceil(hours / 24))
    bbox_str = f"{min_lon},{min_lat},{max_lon},{max_lat}"
    source = "VIIRS_SNPP_NRT"
    return f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{FIRMS_KEY}/{source}/{bbox_str}/{days}"

def now_ksa() -> datetime.datetime:
    return datetime.datetime.now(KSA_TZ)

def now_ksa_str() -> str:
    return now_ksa().strftime("%Y-%m-%d %H:%M KSA")

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
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return []
    header = lines[0].split(",")
    out = []
    for ln in lines[1:]:
        cols = ln.split(",")
        if len(cols) != len(header):
            continue
        row = {header[i]: cols[i] for i in range(len(header))}
        out.append(row)
    return out

# ✅ FIX: معالجة وقت FIRMS الغلط (مثل 2400 أو قيم ناقصة)
def parse_dt_utc(date_str: str, time_str: str) -> Optional[datetime.datetime]:
    try:
        t = str(time_str).strip()

        # تأكد 4 أرقام
        if len(t) < 4:
            t = t.zfill(4)

        hh = int(t[:2])
        mm = int(t[2:])

        # حماية من القيم الغلط
        if hh > 23 or mm > 59:
            return None

        dt = datetime.datetime.fromisoformat(date_str).replace(
            hour=hh,
            minute=mm,
            second=0,
            microsecond=0,
            tzinfo=datetime.timezone.utc
        )
        return dt
    except Exception:
        return None

def within_hours(dt_utc: datetime.datetime, hours: int) -> bool:
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
    return dt_utc >= cutoff

def conf_bucket(conf: str) -> str:
    c = (conf or "").strip().lower()
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
    minc = min_conf.lower().strip()
    if minc == "high":
        return bucketed == "High"
    return bucketed in ("Nominal", "High")

def is_natural_fire(row: dict) -> bool:
    """
    FIRMS VIIRS type:
      0 = presumed vegetation fire
      1 = active volcano
      2 = other static land source (غالباً gas flares)
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

def summarize_region_name(lat: float, lon: float) -> str:
    # تقسيم تقريبي لمناطق السعودية
    if lat < 20.0 and lon < 45.0:
        return "جنوب غرب المملكة"
    if lat < 20.0 and lon >= 45.0:
        return "جنوب المملكة / الربع الخالي"
    if lat >= 24.0 and lon < 42.5:
        return "شمال غرب المملكة"
    if lat >= 24.0 and lon >= 45.0:
        return "المنطقة الشرقية"
    return "وسط/غرب المملكة"

def main():
    state = load_state()
    prev_count = int(state.get("last_count", 0))

    events: List[dict] = []
    per_region_counts: Dict[str, int] = {k: 0 for k in BBOX.keys()}

    for region_name, bbox in BBOX.items():
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

            dt_utc = parse_dt_utc(acq_date, acq_time)
            if dt_utc is None:   # ✅ FIX: تجاهل الوقت الغلط بدل انهيار السكربت
                continue

            if not within_hours(dt_utc, LOOKBACK_HOURS):
                continue

            if not is_natural_fire(row):
                continue

            c_bucket = conf_bucket(row.get("confidence", ""))
            if not pass_conf(MIN_CONFIDENCE, c_bucket):
                continue

            try:
                lat = float(row.get("latitude"))
                lon = float(row.get("longitude"))
            except Exception:
                continue

            frp = None
            try:
                frp = float(row.get("frp")) if row.get("frp") not in (None, "") else None
            except Exception:
                frp = None

            age_min = int((datetime.datetime.now(datetime.timezone.utc) - dt_utc).total_seconds() // 60)

            events.append({
                "region": region_name,
                "lat": lat,
                "lon": lon,
                "frp": frp,
                "conf": c_bucket,
                "age_min": age_min
            })
            per_region_counts[region_name] += 1

    count = len(events)
    delta = count - prev_count

    if count == 0:
        status = "🟢 حالة الرصد: طبيعي"
    else:
        status = "🔴 حالة الرصد: تنبيه"

    if delta > 0:
        trend = f"↑ يتصاعد (+{delta})"
    elif delta < 0:
        trend = f"↓ يتحسن ({delta})"
    else:
        trend = "↔ مستقر (+0)"

    conf_high = sum(1 for e in events if e["conf"] == "High")
    conf_nom = sum(1 for e in events if e["conf"] == "Nominal")
    conf_low = sum(1 for e in events if e["conf"] == "Low")

    top_region = None
    top_region_n = 0
    for rn, n in per_region_counts.items():
        if n > top_region_n:
            top_region_n = n
            top_region = rn

    top_frp = None
    for e in events:
        if e["frp"] is None:
            continue
        if top_frp is None or e["frp"] > top_frp["frp"]:
            top_frp = e

    def key_event(e):
        frp_val = e["frp"] if e["frp"] is not None else -1.0
        return (-frp_val, e["age_min"])

    top3 = sorted(events, key=key_event)[:3]

    lines = []
    lines.append("🔥 رصد حرائق طبيعية — (السعودية | البحر الأحمر | الخليج العربي)")
    lines.append(f"🕒 {now_ksa_str()}")
    lines.append("")
    lines.append(status)
    lines.append(f"📊 عدد الحرائق: {count}")
    lines.append(f"📈 اتجاه الحالة: {trend}")
    lines.append("🛰️ المصدر: NASA FIRMS (VIIRS)")
    lines.append("🧪 فلترة: حرائق طبيعية فقط (استبعاد مصادر صناعية/ثابتة)")
    lines.append("")

    if count > 0:
        lines.append("🏆 الأعلى:")
        if top_region:
            lines.append(f"• 📍 أعلى نطاق: {top_region} ({top_region_n} نقاط)")
        if top_frp:
            approx_region = summarize_region_name(top_frp["lat"], top_frp["lon"])
            lines.append(f"• 🔥 أعلى شدة (FRP): {top_frp['frp']:.1f} MW — {approx_region}")
        lines.append(f"• ✅ الثقة: High ({conf_high}) | Nominal ({conf_nom}) | Low ({conf_low})")
        lines.append("")
        lines.append("📌 أبرز 3 نقاط:")
        for i, e in enumerate(top3, start=1):
            frp_txt = f"{e['frp']:.1f}" if e["frp"] is not None else "—"
            lines.append(f"{i}) {e['lat']:.3f}N, {e['lon']:.3f}E — FRP {frp_txt} | {e['conf']} | {e['age_min']}m ago")
        lines.append("")

    lines.append(f"🔗 عرض الخريطة: {map_link()}")

    tg_send("\n".join(lines))

    state["last_count"] = count
    state["last_update"] = now_ksa_str()
    save_state(state)

if __name__ == "__main__":
    main()
