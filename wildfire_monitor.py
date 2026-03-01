import os
import json
import math
import datetime
from typing import Dict, List, Tuple
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
MIN_CONFIDENCE = "nominal"  # nominal أو high (لو تبي تشدد: خلها "high")
MAX_POINTS_PER_REGION = 200 # حماية

# VIIRS SNPP NRT endpoint (CSV)
# Docs conceptually: FIRMS area CSV via API + key
def firms_url_for_bbox(bbox: Tuple[float, float, float, float], hours: int) -> str:
    min_lon, min_lat, max_lon, max_lat = bbox
    # FIRMS supports area/bbox endpoint; we'll use "area/csv" pattern
    # Note: This URL format matches FIRMS API patterns used widely:
    # /api/area/csv/{key}/{source}/{bbox}/{days}
    # We'll approximate hours by days fraction (hours/24), but FIRMS expects days.
    days = max(1, math.ceil(hours / 24))
    bbox_str = f"{min_lon},{min_lat},{max_lon},{max_lat}"
    source = "VIIRS_SNPP_NRT"  # stable for near-real-time
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
    # FIRMS CSV عادة يبدأ بسطر header
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

def parse_dt_utc(date_str: str, time_str: str) -> datetime.datetime:
    # acq_date=YYYY-MM-DD, acq_time=HHMM
    hh = int(time_str[:2])
    mm = int(time_str[2:])
    dt = datetime.datetime.fromisoformat(date_str).replace(hour=hh, minute=mm, second=0, microsecond=0, tzinfo=datetime.timezone.utc)
    return dt

def within_hours(dt_utc: datetime.datetime, hours: int) -> bool:
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
    return dt_utc >= cutoff

def conf_bucket(conf: str) -> str:
    c = (conf or "").strip().lower()
    # FIRMS VIIRS confidence sometimes is 'l','n','h' or numeric; handle both
    if c in ("h", "high"):
        return "High"
    if c in ("n", "nominal"):
        return "Nominal"
    if c in ("l", "low"):
        return "Low"
    # numeric confidence (0-100) sometimes appears
    try:
        v = float(c)
        if v >= 80:
            return "High"
        if v >= 30:
            return "Nominal"
        return "Low"
    except Exception:
        return "Nominal"

def pass_conf(min_conf: str, conf_bucketed: str) -> bool:
    minc = min_conf.lower().strip()
    if minc == "high":
        return conf_bucketed == "High"
    # nominal: نسمح Nominal+High
    return conf_bucketed in ("Nominal", "High")

def is_natural_fire(row: dict) -> bool:
    """
    فلترة "غير صناعي":
    FIRMS field 'type' for VIIRS:
      0 = presumed vegetation fire
      1 = active volcano
      2 = other static land source (مثل gas flares غالباً)
    نمرر فقط type == 0
    """
    t = row.get("type")
    if t is None:
        # إذا ما وصلنا الحقل، نعتبره طبيعي لكن هذا نادر
        return True
    try:
        return int(float(t)) == 0
    except Exception:
        return True

def map_link() -> str:
    # رابط عام للعرض (مستقر وسهل)
    # تقدر تغيره لاحقًا لعرض bbox محدد
    return "https://firms.modaps.eosdis.nasa.gov/map/"

def summarize_region_name(lat: float, lon: float) -> str:
    # تقسيم تقريبي لمناطق السعودية للتقرير التنفيذي
    # (بدون geocoding خارجي)
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
        r = requests.get(url, timeout=60)
        if r.status_code != 200:
            continue

        rows = parse_csv(r.text)
        # قلّص بيانات المنطقة
        rows = rows[:MAX_POINTS_PER_REGION]

        for row in rows:
            # وقت الالتقاط
            acq_date = row.get("acq_date")
            acq_time = row.get("acq_time")
            if not acq_date or not acq_time:
                continue
            dt_utc = parse_dt_utc(acq_date, acq_time)
            if not within_hours(dt_utc, LOOKBACK_HOURS):
                continue

            # فلترة صناعي/ثابت
            if not is_natural_fire(row):
                continue

            # فلترة الثقة
            c_bucket = conf_bucket(row.get("confidence", ""))
            if not pass_conf(MIN_CONFIDENCE, c_bucket):
                continue

            try:
                lat = float(row.get("latitude"))
                lon = float(row.get("longitude"))
            except Exception:
                continue

            # FRP
            frp = None
            try:
                frp = float(row.get("frp")) if row.get("frp") not in (None, "") else None
            except Exception:
                frp = None

            # age
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

    # إحصائيات الثقة
    conf_high = sum(1 for e in events if e["conf"] == "High")
    conf_nom = sum(1 for e in events if e["conf"] == "Nominal")
    conf_low = sum(1 for e in events if e["conf"] == "Low")

    # أعلى منطقة (حسب العدد)
    top_region = None
    top_region_n = 0
    for rn, n in per_region_counts.items():
        if n > top_region_n:
            top_region_n = n
            top_region = rn

    # أعلى FRP
    top_frp = None
    for e in events:
        if e["frp"] is None:
            continue
        if top_frp is None or e["frp"] > top_frp["frp"]:
            top_frp = e

    # أبرز 3 نقاط (حسب FRP ثم الحداثة)
    def key_event(e):
        frp = e["frp"] if e["frp"] is not None else -1.0
        return (-frp, e["age_min"])
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
            frp_val = top_frp["frp"]
            approx_region = summarize_region_name(top_frp["lat"], top_frp["lon"])
            lines.append(f"• 🔥 أعلى شدة (FRP): {frp_val:.1f} MW — {approx_region}")
        lines.append(f"• ✅ الثقة: High ({conf_high}) | Nominal ({conf_nom}) | Low ({conf_low})")
        lines.append("")
        lines.append("📌 أبرز 3 نقاط:")
        for i, e in enumerate(top3, start=1):
            frp_txt = f"{e['frp']:.1f}" if e["frp"] is not None else "—"
            lines.append(f"{i}) {e['lat']:.3f}N, {e['lon']:.3f}E — FRP {frp_txt} | {e['conf']} | {e['age_min']}m ago")
        lines.append("")

    lines.append(f"🔗 عرض الخريطة: {map_link()}")

    tg_send("\n".join(lines))

    # حفظ الحالة
    state["last_count"] = count
    state["last_update"] = now_ksa_str()
    save_state(state)

if __name__ == "__main__":
    main()
