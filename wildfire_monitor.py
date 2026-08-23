import os
import json
import math
import datetime
import time
import requests

# ============================================================
# 🔥 Saudi Wildfire Intelligence V5.0
# Intelligent Fire Intelligence Engine
# NASA FIRMS + VIIRS
# ============================================================

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
FIRMS_KEY = os.environ["FIRMS_API_KEY"]

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))

STATE_FILE = "wildfire_state_v5.json"

# ============================================================
# إعدادات الرصد
# ============================================================

# Bounding Box واسع للسعودية فقط كمرحلة V5.0
BBOX = (
    34.5,   # min longitude
    16.0,   # min latitude
    55.8,   # max longitude
    32.6    # max latitude
)

# الأقمار المستخدمة
SOURCES = [
    "VIIRS_SNPP_NRT",
    "VIIRS_NOAA20_NRT",
]

# FRP الأدنى
MIN_FRP = 3.0

# أقصى عمر للبيانات
MAX_AGE_HOURS = 24

# مسافة التجميع بالكيلومتر
CLUSTER_RADIUS_KM = 2.5

# الفترة الزمنية للتجميع
CLUSTER_TIME_MINUTES = 180

# أقل عدد نقاط لرفع الثقة
MULTI_POINT_CLUSTER = 2

# عدد المواقع المعروضة
TOP_CLUSTERS = 5

# ============================================================
# Headers
# ============================================================

HTTP_HEADERS = {
    "User-Agent": "Saudi-Wildfire-Intelligence-V5/1.0",
    "Accept": "text/csv,*/*",
    "Connection": "close",
}

# ============================================================
# الوقت
# ============================================================

def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def now_ksa():
    return datetime.datetime.now(KSA_TZ).strftime(
        "%Y-%m-%d %H:%M KSA"
    )


# ============================================================
# State
# ============================================================

def load_state():

    if not os.path.exists(STATE_FILE):
        return {
            "seen": {},
            "last_clusters": {},
            "last_run": None
        }

    try:
        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            return json.load(f)

    except Exception:
        return {
            "seen": {},
            "last_clusters": {},
            "last_run": None
        }


def save_state(state):

    # تنظيف السجل القديم
    cutoff = now_utc() - datetime.timedelta(hours=48)

    cleaned = {}

    for key, value in state.get("seen", {}).items():

        try:
            dt = datetime.datetime.fromisoformat(value)

            if dt >= cutoff:
                cleaned[key] = value

        except Exception:
            pass

    state["seen"] = cleaned
    state["last_run"] = now_ksa()

    with open(
        STATE_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            state,
            f,
            ensure_ascii=False,
            indent=2
        )


# ============================================================
# Telegram
# ============================================================

def tg_send(text):

    url = (
        f"https://api.telegram.org/bot"
        f"{BOT}/sendMessage"
    )

    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "disable_web_page_preview": True
    }

    response = requests.post(
        url,
        json=payload,
        timeout=30
    )

    response.raise_for_status()


# ============================================================
# CSV Parser
# ============================================================

def parse_csv(text):

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    if len(lines) < 2:
        return []

    header = lines[0].split(",")

    rows = []

    for line in lines[1:]:

        columns = line.split(",")

        if len(columns) != len(header):
            continue

        rows.append(
            {
                header[i]: columns[i]
                for i in range(len(header))
            }
        )

    return rows


# ============================================================
# FIRMS API
# ============================================================

def get_firms_rows(source):

    min_lon, min_lat, max_lon, max_lat = BBOX

    bbox = (
        f"{min_lon},"
        f"{min_lat},"
        f"{max_lon},"
        f"{max_lat}"
    )

    url = (
        f"https://firms.modaps.eosdis.nasa.gov/"
        f"api/area/csv/"
        f"{FIRMS_KEY}/"
        f"{source}/"
        f"{bbox}/1"
    )

    last_error = None

    for attempt in range(3):

        try:

            response = requests.get(
                url,
                headers=HTTP_HEADERS,
                timeout=60
            )

            if response.status_code == 200:

                return parse_csv(
                    response.text
                )

            last_error = (
                f"HTTP {response.status_code}"
            )

        except Exception as e:

            last_error = str(e)

        time.sleep(3)

    print(
        f"❌ FIRMS API error ({source}): "
        f"{last_error}"
    )

    return []


# ============================================================
# السعودية - V5.0
#
# ملاحظة:
# هذه مرحلة أولى تستخدم Bounding Box.
# لا نستخدم استثناءات مثل:
# lat < 27 and lon > 50
# لأنها قد تستبعد مواقع سعودية صحيحة.
# ============================================================

def is_saudi_bbox(lat, lon):

    min_lon, min_lat, max_lon, max_lat = BBOX

    return (
        min_lat <= lat <= max_lat
        and
        min_lon <= lon <= max_lon
    )


# ============================================================
# التاريخ والوقت
# ============================================================

def parse_acquisition_datetime(
    date_value,
    time_value
):

    try:

        date_value = str(
            date_value
        ).strip()

        time_value = str(
            time_value
        ).strip()

        time_value = time_value.zfill(4)

        hour = int(
            time_value[:2]
        )

        minute = int(
            time_value[2:4]
        )

        if hour > 23 or minute > 59:
            return None

        return datetime.datetime(
            *map(
                int,
                date_value.split("-")
            ),
            hour,
            minute,
            tzinfo=datetime.timezone.utc
        )

    except Exception:

        return None


# ============================================================
# Confidence
# ============================================================

def confidence_score(value):

    value = str(
        value or ""
    ).strip().lower()

    if value in ("h", "high"):
        return 90

    if value in ("n", "nominal"):
        return 65

    if value in ("l", "low"):
        return 35

    try:

        number = float(value)

        if number >= 80:
            return 90

        if number >= 30:
            return 65

        return 35

    except Exception:

        return 50


def confidence_ar(score):

    if score >= 80:
        return "عالية"

    if score >= 60:
        return "متوسطة"

    return "منخفضة"


# ============================================================
# Haversine
# ============================================================

def distance_km(
    lat1,
    lon1,
    lat2,
    lon2
):

    earth_radius = 6371.0

    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)

    dlat = lat2 - lat1

    dlon = math.radians(
        lon2 - lon1
    )

    a = (
        math.sin(dlat / 2) ** 2
        +
        math.cos(lat1)
        *
        math.cos(lat2)
        *
        math.sin(dlon / 2) ** 2
    )

    return (
        earth_radius
        *
        2
        *
        math.atan2(
            math.sqrt(a),
            math.sqrt(1 - a)
        )
    )


# ============================================================
# Natural Fire Filter
# ============================================================

def is_natural_fire(row):

    value = row.get("type")

    if value in (None, ""):
        return True

    try:

        fire_type = int(
            float(value)
        )

        # 0 = presumed vegetation fire
        return fire_type == 0

    except Exception:

        return True


# ============================================================
# تنظيف البيانات
# ============================================================

def normalize_rows(rows):

    events = []

    current_time = now_utc()

    for row in rows:

        try:

            lat = float(
                row["latitude"]
            )

            lon = float(
                row["longitude"]
            )

        except Exception:

            continue

        if not is_saudi_bbox(
            lat,
            lon
        ):
            continue

        if not is_natural_fire(row):
            continue

        acquisition = (
            parse_acquisition_datetime(
                row.get("acq_date"),
                row.get("acq_time")
            )
        )

        if acquisition is None:
            continue

        age_hours = (
            current_time - acquisition
        ).total_seconds() / 3600

        if age_hours < 0:
            age_hours = 0

        if age_hours > MAX_AGE_HOURS:
            continue

        try:

            frp = float(
                row.get("frp", 0)
            )

        except Exception:

            frp = 0

        if frp < MIN_FRP:
            continue

        confidence = confidence_score(
            row.get("confidence")
        )

        events.append(
            {
                "lat": lat,
                "lon": lon,
                "frp": frp,
                "confidence": confidence,
                "date": row.get("acq_date"),
                "time": row.get("acq_time"),
                "datetime": acquisition,
                "age_hours": age_hours
            }
        )

    return events


# ============================================================
# إزالة التكرار
# ============================================================

def remove_duplicates(events):

    unique = {}

    for event in events:

        key = (
            round(event["lat"], 3),
            round(event["lon"], 3),
            event["date"],
            event["time"]
        )

        if key not in unique:

            unique[key] = event

        else:

            # نحتفظ بالأعلى FRP
            if event["frp"] > unique[key]["frp"]:

                unique[key] = event

    return list(
        unique.values()
    )


# ============================================================
# Clustering
# ============================================================

def cluster_events(events):

    clusters = []

    # ترتيب من الأقوى للأضعف
    events = sorted(
        events,
        key=lambda x: x["frp"],
        reverse=True
    )

    for event in events:

        assigned = False

        for cluster in clusters:

            center = cluster["center"]

            distance = distance_km(
                event["lat"],
                event["lon"],
                center["lat"],
                center["lon"]
            )

            time_difference = abs(
                (
                    event["datetime"]
                    -
                    cluster["latest"]
                ).total_seconds()
            ) / 60

            if (
                distance
                <= CLUSTER_RADIUS_KM
                and
                time_difference
                <= CLUSTER_TIME_MINUTES
            ):

                cluster["events"].append(
                    event
                )

                cluster["total_frp"] += (
                    event["frp"]
                )

                cluster["max_frp"] = max(
                    cluster["max_frp"],
                    event["frp"]
                )

                cluster["latest"] = max(
                    cluster["latest"],
                    event["datetime"]
                )

                # إعادة حساب المركز
                count = len(
                    cluster["events"]
                )

                cluster["center"]["lat"] = (
                    sum(
                        e["lat"]
                        for e in cluster["events"]
                    ) / count
                )

                cluster["center"]["lon"] = (
                    sum(
                        e["lon"]
                        for e in cluster["events"]
                    ) / count
                )

                assigned = True

                break

        if not assigned:

            clusters.append(
                {
                    "center": {
                        "lat": event["lat"],
                        "lon": event["lon"]
                    },
                    "events": [event],
                    "total_frp": event["frp"],
                    "max_frp": event["frp"],
                    "latest": event["datetime"]
                }
            )

    return clusters


# ============================================================
# Risk Engine
# ============================================================

def calculate_risk(cluster):

    count = len(
        cluster["events"]
    )

    max_frp = cluster["max_frp"]

    total_frp = cluster["total_frp"]

    avg_confidence = (
        sum(
            e["confidence"]
            for e in cluster["events"]
        )
        /
        count
    )

    # -------------------------------
    # FRP Score
    # -------------------------------

    if max_frp >= 150:
        frp_score = 100

    elif max_frp >= 100:
        frp_score = 90

    elif max_frp >= 70:
        frp_score = 80

    elif max_frp >= 40:
        frp_score = 65

    elif max_frp >= 20:
        frp_score = 50

    elif max_frp >= 10:
        frp_score = 35

    else:
        frp_score = 20

    # -------------------------------
    # Cluster Score
    # -------------------------------

    if count >= 10:
        cluster_score = 100

    elif count >= 6:
        cluster_score = 85

    elif count >= 3:
        cluster_score = 70

    elif count >= 2:
        cluster_score = 50

    else:
        cluster_score = 20

    # -------------------------------
    # Confidence
    # -------------------------------

    confidence_score_value = avg_confidence

    # -------------------------------
    # Final Score
    # -------------------------------

    risk = (
        frp_score * 0.45
        +
        cluster_score * 0.30
        +
        confidence_score_value * 0.25
    )

    risk = round(
        min(
            100,
            max(
                0,
                risk
            )
        )
    )

    if risk >= 80:
        level = "حرج"
        emoji = "🔴"

    elif risk >= 60:
        level = "مرتفع"
        emoji = "🟠"

    elif risk >= 40:
        level = "متوسط"
        emoji = "🟡"

    else:
        level = "منخفض"
        emoji = "🟢"

    return {
        "score": risk,
        "level": level,
        "emoji": emoji,
        "confidence": round(
            avg_confidence
        ),
        "max_frp": max_frp,
        "total_frp": total_frp,
        "count": count
    }


# ============================================================
# Cluster ID
# ============================================================

def cluster_id(cluster):

    lat = round(
        cluster["center"]["lat"],
        2
    )

    lon = round(
        cluster["center"]["lon"],
        2
    )

    date = cluster["latest"].strftime(
        "%Y-%m-%d"
    )

    return (
        f"{lat}_{lon}_{date}"
    )


# ============================================================
# Google Maps
# ============================================================

def google_maps(lat, lon):

    return (
        "https://www.google.com/maps"
        f"?q={lat},{lon}"
    )


# ============================================================
# المنطقة التقريبية
#
# V5.0 لا يستخدم Polygon رسمي.
# لذلك نكتب "تحديد إداري لاحقاً".
# ============================================================

def approximate_region(lat, lon):

    if lat >= 28:
        return "شمال المملكة"

    if lat >= 24 and lon < 44:
        return "منطقة المدينة المنورة / شمال غرب المملكة"

    if lat >= 22 and lon < 48:
        return "منطقة الرياض / وسط المملكة"

    if lat < 22 and lon < 44:
        return "منطقة جازان / جنوب غرب المملكة"

    if lon >= 48:
        return "شرق المملكة"

    return "المملكة العربية السعودية"


# ============================================================
# تقرير عدم وجود حرائق
# ============================================================

def send_no_fire_report(
    raw_count,
    normalized_count
):

    message = f"""
🟢 رصد حرائق السعودية V5

🕒 {now_ksa()}

✅ لا توجد بؤر حرائق تستوفي معايير التنبيه حالياً.

📊 بيانات FIRMS المستلمة: {raw_count}
🧪 النقاط بعد التحليل: {normalized_count}
🔥 البؤر المكتشفة: 0

🛰️ المصدر: NASA FIRMS / VIIRS
🤖 محرك التحليل: V5 Intelligent Fire Intelligence Engine

الحالة: النظام يعمل بشكل طبيعي
"""

    tg_send(
        message.strip()
    )


# ============================================================
# التقرير الرئيسي
# ============================================================

def send_fire_report(
    clusters,
    raw_count,
    normalized_count
):

    # ترتيب حسب الخطورة
    clusters = sorted(
        clusters,
        key=lambda c: (
            c["risk"]["score"],
            c["risk"]["max_frp"],
            c["risk"]["count"]
        ),
        reverse=True
    )

    top = clusters[:TOP_CLUSTERS]

    highest = top[0]

    lat = highest["center"]["lat"]
    lon = highest["center"]["lon"]

    risk = highest["risk"]

    region = approximate_region(
        lat,
        lon
    )

    message = []

    message.append(
        "🔥 رصد حرائق السعودية V5"
    )

    message.append(
        f"🕒 {now_ksa()}"
    )

    message.append("")

    message.append(
        f"🚨 البؤر المكتشفة: {len(clusters)}"
    )

    message.append(
        f"📊 النقاط الحرارية المحللة: {normalized_count}"
    )

    message.append(
        f"📡 بيانات FIRMS المستلمة: {raw_count}"
    )

    message.append("")

    message.append(
        "⚠️ أعلى مستوى خطورة:"
    )

    message.append(
        f"{risk['emoji']} {risk['level']} "
        f"— {risk['score']}/100"
    )

    message.append("")

    message.append(
        "📌 أبرز البؤر:"
    )

    for index, cluster in enumerate(
        top,
        start=1
    ):

        c = cluster["center"]

        r = cluster["risk"]

        region_name = approximate_region(
            c["lat"],
            c["lon"]
        )

        confidence = confidence_ar(
            r["confidence"]
        )

        message.append(
            f"""
{index}) {r['emoji']} {r['level']} — {r['score']}/100
📍 {c['lat']:.4f}, {c['lon']:.4f}
🗺️ النطاق: {region_name}
🔥 عدد النقاط: {r['count']}
⚡ أعلى FRP: {r['max_frp']:.1f} MW
📊 إجمالي FRP: {r['total_frp']:.1f} MW
🎯 الثقة: {confidence}
"""
        )

    message.append(
        "📍 موقع أعلى بؤرة:"
    )

    message.append(
        google_maps(
            lat,
            lon
        )
    )

    message.append("")

    message.append(
        "🛰️ مصدر البيانات:"
    )

    message.append(
        "NASA FIRMS / VIIRS"
    )

    message.append(
        "🤖 محرك التحليل:"
    )

    message.append(
        "V5 Intelligent Fire Intelligence Engine"
    )

    message.append("")

    message.append(
        "🗺️ خريطة FIRMS:"
    )

    message.append(
        "https://firms.modaps.eosdis.nasa.gov/map/"
    )

    tg_send(
        "\n".join(
            message
        )
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)

    print(
        "🔥 Saudi Wildfire Intelligence V5.0"
    )

    print(
        f"🕒 {now_ksa()}"
    )

    print("=" * 60)

    state = load_state()

    seen = state.get(
        "seen",
        {}
    )

    all_rows = []

    # ========================================================
    # جلب البيانات
    # ========================================================

    for source in SOURCES:

        print(
            f"📡 Reading {source}..."
        )

        rows = get_firms_rows(
            source
        )

        print(
            f"   Rows: {len(rows)}"
        )

        all_rows.extend(
            rows
        )

    raw_count = len(
        all_rows
    )

    print(
        f"📊 Total FIRMS rows: {raw_count}"
    )

    # ========================================================
    # Normalize
    # ========================================================

    events = normalize_rows(
        all_rows
    )

    print(
        f"🧪 After filtering: {len(events)}"
    )

    # ========================================================
    # Duplicate removal
    # ========================================================

    events = remove_duplicates(
        events
    )

    print(
        f"🔁 After duplicates: {len(events)}"
    )

    # ========================================================
    # NEW EVENT DETECTION
    # ========================================================

    new_events = []

    for event in events:

        uid = (
            f"{round(event['lat'], 3)}_"
            f"{round(event['lon'], 3)}_"
            f"{event['date']}_"
            f"{event['time']}"
        )

        if uid in seen:
            continue

        seen[uid] = now_utc().isoformat()

        new_events.append(
            event
        )

    print(
        f"🆕 New events: {len(new_events)}"
    )

    # ========================================================
    # مهم:
    # V5 يحلل البيانات الحالية كلها،
    # وليس فقط النقاط الجديدة.
    # ========================================================

    clusters = cluster_events(
        events
    )

    print(
        f"🔥 Clusters: {len(clusters)}"
    )

    # ========================================================
    # Risk
    # ========================================================

    valid_clusters = []

    for cluster in clusters:

        cluster["risk"] = (
            calculate_risk(
                cluster
            )
        )

        valid_clusters.append(
            cluster
        )

    # ========================================================
    # إزالة البؤر منخفضة جداً
    # ========================================================

    alert_clusters = []

    for cluster in valid_clusters:

        risk = cluster["risk"]

        # بؤرة من نقطة واحدة ضعيفة جداً
        # لا تعتبر تنبيهاً رئيسياً
        if (
            risk["score"] < 40
            and
            risk["count"] == 1
        ):
            continue

        alert_clusters.append(
            cluster
        )

    print(
        f"🚨 Alert clusters: "
        f"{len(alert_clusters)}"
    )

    # ========================================================
    # إرسال التقرير
    # ========================================================

    if not alert_clusters:

        send_no_fire_report(
            raw_count,
            len(events)
        )

    else:

        send_fire_report(
            alert_clusters,
            raw_count,
            len(events)
        )

    # ========================================================
    # حفظ State
    # ========================================================

    state["seen"] = seen

    save_state(
        state
    )

    print(
        "✅ V5 completed successfully"
    )


# ============================================================

if __name__ == "__main__":
    main()
