# wildfire_monitor.py
import os
import io
import json
import math
import csv
import hashlib
import datetime
from typing import Dict, Any, List, Tuple

import requests
import matplotlib.pyplot as plt

# =========================
# إعدادات عامة
# =========================
BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
FIRMS_API_KEY = os.environ["FIRMS_API_KEY"]

STATE_FILE = "wildfire_state.json"
KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))

# نطاق الرصد: السعودية + البحر الأحمر + الخليج العربي (تقريب واسع)
REGION_BOX = (12.0, 34.5, 33.0, 57.5)  # (min_lat, max_lat, min_lon, max_lon)

# فلترة متوازنة
BASE_MIN_CONF = 70
COAST_MIN_CONF = 80
COAST_MIN_FRP = 8.0

# حد أعلى لعدد النقاط في التنبيه الواحد
MAX_ALERTS = 25


# =========================
# أدوات مساعدة
# =========================
def safe_float(v) -> float:
    """يحاول يحول أي قيمة لرقم. إذا فشل يرجع 0.0 (يعالج confidence='n' وغيرها)."""
    try:
        if v is None:
            return 0.0
        s = str(v).strip()
        if s == "" or s.lower() in {"n", "na", "nan", "null", "none"}:
            return 0.0
        return float(s)
    except Exception:
        return 0.0


def in_box(lat: float, lon: float, box: Tuple[float, float, float, float]) -> bool:
    return box[0] <= lat <= box[1] and box[2] <= lon <= box[3]


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def maps_link(lat: float, lon: float) -> str:
    return f"https://maps.google.com/?q={lat:.5f},{lon:.5f}"


# =========================
# استبعاد حضري/صناعي (تقريبي عملي)
# =========================
URBAN_BOXES = [
    (24.2, 25.2, 46.1, 47.2),  # الرياض
    (21.1, 21.9, 39.0, 39.5),  # جدة
    (21.2, 21.6, 39.6, 40.0),  # مكة (تقريب)
    (26.2, 26.6, 50.0, 50.4),  # الدمام/الخبر (تقريب)
    (26.6, 27.2, 49.8, 50.4),  # الجبيل (تقريب)
    (24.4, 24.7, 39.5, 39.8),  # ينبع (تقريب)
    (24.0, 24.3, 38.0, 38.3),  # رابغ (تقريب)
    (16.8, 17.2, 42.4, 42.8),  # جازان (تقريب)
]

INDUSTRIAL_HOTSPOTS = [
    ("Ras Tanura", 26.643, 50.162, 25),
    ("Jubail Industrial", 27.012, 49.650, 30),
    ("Dammam Port", 26.434, 50.103, 20),
    ("Yanbu Industrial", 24.089, 38.062, 30),
    ("Jeddah Islamic Port", 21.485, 39.173, 20),
    ("Rabigh Petrochem", 22.789, 39.034, 25),
    ("Jazan Port/Industrial", 16.889, 42.556, 25),
]

# شرائط ساحلية تقريبية (لاستبعاد false positives البحرية بشكل "متوازن")
RED_SEA_COAST_STRIP = (16.0, 30.5, 33.0, 39.8)   # البحر الأحمر
GULF_COAST_STRIP = (24.0, 29.5, 47.5, 56.5)       # الخليج العربي


def in_urban(lat: float, lon: float) -> bool:
    return any(in_box(lat, lon, b) for b in URBAN_BOXES)


def near_industrial(lat: float, lon: float) -> bool:
    for _, hlat, hlon, rkm in INDUSTRIAL_HOTSPOTS:
        if haversine_km(lat, lon, hlat, hlon) <= rkm:
            return True
    return False


def is_probably_coastal(lat: float, lon: float) -> bool:
    return in_box(lat, lon, RED_SEA_COAST_STRIP) or in_box(lat, lon, GULF_COAST_STRIP)


def is_wildfire_candidate(f: Dict[str, Any]) -> bool:
    lat = safe_float(f.get("latitude"))
    lon = safe_float(f.get("longitude"))
    conf = safe_float(f.get("confidence"))
    frp = safe_float(f.get("frp"))

    # 0) نطاق الرصد
    if not in_box(lat, lon, REGION_BOX):
        return False

    # 1) ثقة أساسية
    if conf < BASE_MIN_CONF:
        return False

    # 2) حضري/صناعي
    if in_urban(lat, lon):
        return False

    # 3) منشآت/موانئ/نفط (قوي)
    if near_industrial(lat, lon):
        return False

    # 4) ساحلي متوازن: لا نرفض تلقائيًا
    if is_probably_coastal(lat, lon):
        # إذا ضعيف غالبًا false positive بحري/سفن
        if frp < COAST_MIN_FRP:
            return False
        # إذا الثقة مو عالية جدًا في الساحل غالبًا false positive
        if conf < COAST_MIN_CONF:
            return False

    return True


# =========================
# Telegram
# =========================
def tg_send_message(text: str) -> None:
    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    r = requests.post(
        url,
        json={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True},
        timeout=30,
    )
    r.raise_for_status()


def tg_send_photo(png_bytes: bytes, caption: str = "") -> None:
    url = f"https://api.telegram.org/bot{BOT}/sendPhoto"
    files = {"photo": ("wildfires.png", png_bytes, "image/png")}
    data = {"chat_id": CHAT_ID, "caption": caption}
    r = requests.post(url, data=data, files=files, timeout=60)
    r.raise_for_status()


# =========================
# State (منع التكرار)
# =========================
def load_state() -> Dict[str, Any]:
    if not os.path.exists(STATE_FILE):
        return {"seen": {}}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"seen": {}}


def save_state(state: Dict[str, Any]) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def fire_id(f: Dict[str, Any]) -> str:
    s = f'{safe_float(f.get("latitude")):.5f},{safe_float(f.get("longitude")):.5f}|{f.get("acq_date","")}|{f.get("acq_time","")}|{f.get("satellite","")}'
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


# =========================
# NASA FIRMS Fetch
# =========================
def fetch_firms(source: str, days: int = 2) -> List[Dict[str, Any]]:
    # API: /api/area/csv/{MAP_KEY}/{SOURCE}/{BBOX}/{DAYS}
    min_lat, max_lat, min_lon, max_lon = REGION_BOX
    bbox = f"{min_lon},{min_lat},{max_lon},{max_lat}"
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{FIRMS_API_KEY}/{source}/{bbox}/{days}"

    r = requests.get(url, timeout=60)
    r.raise_for_status()

    text = r.text.strip()
    if not text:
        return []

    reader = csv.DictReader(text.splitlines())
    return list(reader)


def normalize_fire(row: Dict[str, Any], source: str) -> Dict[str, Any]:
    # نرجّع حقول موحدة ونستخدم safe_float لتجنب 'n' وغيرها
    return {
        "latitude": safe_float(row.get("latitude")),
        "longitude": safe_float(row.get("longitude")),
        "acq_date": row.get("acq_date", ""),
        "acq_time": row.get("acq_time", ""),
        "confidence": safe_float(row.get("confidence")),
        "frp": safe_float(row.get("frp")),
        "satellite": row.get("satellite", source),
        "source": source,
    }


# =========================
# رسم "خريطة نقاط" (PNG)
# =========================
def make_points_image(fires: List[Dict[str, Any]]) -> bytes:
    lats = [safe_float(f.get("latitude")) for f in fires]
    lons = [safe_float(f.get("longitude")) for f in fires]

    # في حال كانت النقاط قليلة جدًا
    min_lat, max_lat = min(lats) - 1, max(lats) + 1
    min_lon, max_lon = min(lons) - 1, max(lons) + 1

    fig = plt.figure(figsize=(7.5, 7.5))
    ax = plt.gca()
    ax.set_title("🔥 Wildfire Detections (Filtered, Balanced)")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_xlim(min_lon, max_lon)
    ax.set_ylim(min_lat, max_lat)
    ax.grid(True)

    ax.scatter(lons, lats)

    for i, f in enumerate(fires, start=1):
        ax.text(safe_float(f.get("longitude")), safe_float(f.get("latitude")), f" {i}", fontsize=10)

    buf = io.BytesIO()
    plt.tight_layout()
    fig.savefig(buf, format="png", dpi=170)
    plt.close(fig)
    return buf.getvalue()


# =========================
# إرسال Bundle (C): صورة + روابط
# =========================
def send_fire_alert_bundle(fires: List[Dict[str, Any]]) -> None:
    now = datetime.datetime.now(KSA_TZ).strftime("%Y-%m-%d %H:%M KSA")

    # رتّب وأخذ أفضل N
    fires_sorted = sorted(
        fires,
        key=lambda x: (safe_float(x.get("confidence")), safe_float(x.get("frp"))),
        reverse=True,
    )[:MAX_ALERTS]

    png = make_points_image(fires_sorted)

    tg_send_photo(
        png,
        caption=f"🔥 خريطة الحرائق الطبيعية (متوازن)\n📍 السعودية + البحر الأحمر + الخليج\n🕒 {now}\n📊 العدد: {len(fires_sorted)}"
    )

    lines = [
        "🔥 تقرير الحرائق الطبيعية (متوازن)",
        "📍 النطاق: السعودية + البحر الأحمر + الخليج العربي",
        f"📊 العدد: {len(fires_sorted)}",
        f"🕒 آخر تحديث: {now}",
        ""
    ]

    for i, f in enumerate(fires_sorted, start=1):
        frp = safe_float(f.get("frp"))
        conf = safe_float(f.get("confidence"))
        sat = f.get("satellite", "VIIRS")
        lat = safe_float(f.get("latitude"))
        lon = safe_float(f.get("longitude"))

        lines.append(f"{i}) 🔥 FRP: {frp:.1f} MW | ثقة: {conf:.0f} | 📡 {sat}")
        lines.append(f"📍 {maps_link(lat, lon)}")
        lines.append("")

    tg_send_message("\n".join(lines))


# =========================
# MAIN
# =========================
def main():
    state = load_state()
    seen = state.get("seen", {})

    sources = [
        "VIIRS_SNPP_NRT",
        "VIIRS_NOAA20_NRT",
    ]

    fires: List[Dict[str, Any]] = []
    for src in sources:
        rows = fetch_firms(src, days=2)
        for r in rows:
            fires.append(normalize_fire(r, src))

    # فلترة
    filtered = [f for f in fires if is_wildfire_candidate(f)]

    # جديد فقط (منع تكرار)
    new_fires = []
    for f in filtered:
        fid = fire_id(f)
        if fid in seen:
            continue
        new_fires.append(f)
        seen[fid] = datetime.datetime.now(KSA_TZ).isoformat()

    state["seen"] = seen
    save_state(state)

    if new_fires:
        send_fire_alert_bundle(new_fires)
    else:
        tg_send_message("✅ لا توجد حرائق طبيعية جديدة مطابقة للفلترة (متوازن) ضمن السعودية/البحر الأحمر/الخليج.")


if __name__ == "__main__":
    main()
