import os
import json
import math
import csv
import io
import datetime
import time
import requests

# ============================================================
# 🔥 Saudi Wildfire Intelligence V5.1 AI
# Intelligent Wildfire Detection & Risk Engine
# NASA FIRMS + VIIRS
# ============================================================

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
FIRMS_KEY = os.environ["FIRMS_API_KEY"]

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
UTC = datetime.timezone.utc

STATE_FILE = "wildfire_state_v51.json"

# ============================================================
# 🇸🇦 نطاق الرصد
# ============================================================

BBOX = (
    34.5,   # min longitude
    16.0,   # min latitude
    55.8,   # max longitude
    32.6    # max latitude
)

# ============================================================
# 🛰️ الأقمار الصناعية
# ============================================================

SOURCES = [
    "VIIRS_SNPP_NRT",
    "VIIRS_NOAA20_NRT",
]

# ============================================================
# ⚙️ إعدادات الذكاء والتحليل
# ============================================================

MIN_FRP = 3.0

MAX_AGE_HOURS = 24

CLUSTER_RADIUS_KM = 2.5

CLUSTER_TIME_MINUTES = 180

# الحد الأدنى لاعتبار البؤرة تنبيهًا
MIN_ALERT_SCORE = 45

# إذا كانت نقطة واحدة وقوتها ضعيفة لا نرسل تنبيه
SINGLE_POINT_MIN_SCORE = 60

# عدد البؤر التي تظهر في التقرير
TOP_CLUSTERS = 5

# إرسال الحالة المستقرة؟
SEND_NORMAL_STATUS = True

# ============================================================
# 🌐 الاتصال
# ============================================================

HTTP_HEADERS = {
    "User-Agent": "Saudi-Wildfire-Intelligence-V5.1-AI/1.0",
    "Accept": "text/csv,*/*",
    "Connection": "close",
}

# ============================================================
# 🇸🇦 Polygon مبسط للسعودية
#
# الهدف:
# منع معظم النقاط الواقعة خارج المملكة التي تدخل بسبب BBOX.
#
# تم تصميمه ليكون محافظًا ولا يستبعد الأطراف السعودية بسهولة.
# ============================================================

SAUDI_POLYGON = [
    (32.15, 34.60),
    (31.40, 36.00),
    (31.00, 37.00),
    (30.00, 39.00),
    (29.00, 41.00),
    (28.00, 43.00),
    (27.50, 45.00),
    (27.80, 48.00),
    (28.00, 50.00),
    (27.70, 51.50),
    (26.50, 52.50),
    (25.50, 54.00),
    (24.50, 55.20),
    (23.00, 55.80),
    (22.00, 55.20),
    (21.00, 55.00),
    (20.00, 53.50),
    (19.00, 51.00),
    (18.00, 49.00),
    (17.00, 47.00),
    (16.00, 44.00),
    (16.00, 42.00),
    (17.00, 40.00),
    (18.00, 39.00),
    (19.00, 38.50),
    (20.00, 38.00),
    (21.00, 37.50),
    (22.00, 36.50),
    (23.00, 35.50),
    (24.00, 35.00),
    (25.00, 35.00),
    (26.00, 35.20),
    (27.00, 35.40),
    (28.00, 35.50),
    (29.00, 35.80),
    (30.00, 36.00),
    (31.00, 35.50),
]

# ============================================================
# 🕒 الوقت
# ============================================================

def now_utc():
    return datetime.datetime.now(UTC)


def now_ksa():
    return datetime.datetime.now(KSA_TZ).strftime(
        "%Y-%m-%d %H:%M KSA"
    )


# ============================================================
# 📁 State
# ============================================================

def load_state():

    if not os.path.exists(STATE_FILE):
        return {
            "seen": {},
            "clusters": {},
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
            "clusters": {},
            "last_run": None
        }


def save_state(state):

    cutoff = now_utc() - datetime.timedelta(hours=48)

    cleaned_seen = {}

    for key, value in state.get(
        "seen",
        {}
    ).items():

        try:

            dt = datetime.datetime.fromisoformat(
                value
            )

            if dt >= cutoff:
                cleaned_seen[key] = value

        except Exception:
            pass

    state["seen"] = cleaned_seen

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
# 📲 Telegram
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
# 📄 CSV Parser
# ============================================================

def parse_csv(text):

    try:

        reader = csv.DictReader(
            io.StringIO(text)
        )

        return [
            dict(row)
            for row in reader
            if row
        ]

    except Exception:

        return []


# ============================================================
# 🛰️ FIRMS API
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
        "https://firms.modaps.eosdis.nasa.gov/"
        f"api/area/csv/"
        f"{FIRMS_KEY}/"
        f"{source}/"
        f"{bbox}/1"
    )

    last_error = None

    for attempt in range(1, 4):

        try:

            print(
                f"   محاولة الاتصال {attempt}/3..."
            )

            response = requests.get(
                url,
                headers=HTTP_HEADERS,
                timeout=60
            )

            if response.status_code == 200:

                rows = parse_csv(
                    response.text
                )

                return rows

            last_error = (
                f"HTTP {response.status_code}"
            )

        except Exception as e:

            last_error = str(e)

        if attempt < 3:
            time.sleep(4)

    print(
        f"❌ FIRMS API error ({source}): "
        f"{last_error}"
    )

    return []


# ============================================================
# 🇸🇦 Point in Polygon
# ============================================================

def point_in_polygon(lat, lon):

    inside = False

    polygon = SAUDI_POLYGON

    j = len(polygon) - 1

    for i in range(len(polygon)):

        lat_i, lon_i = polygon[i]
        lat_j, lon_j = polygon[j]

        intersects = (
            (
                lon_i > lon
            ) != (
                lon_j > lon
            )
        ) and (
            lat
            <
            (
                lat_j - lat_i
            )
            *
            (
                lon - lon_i
            )
            /
            (
                lon_j - lon_i
                if lon_j != lon_i
                else 1e-12
            )
            +
            lat_i
        )

        if intersects:
            inside = not inside

        j = i

    return inside


# ============================================================
# 🇸🇦 فلترة السعودية
# ============================================================

def is_saudi(lat, lon):

    min_lon, min_lat, max_lon, max_lat = BBOX

    # أول فلترة سريعة
    if not (
        min_lat <= lat <= max_lat
        and
        min_lon <= lon <= max_lon
    ):
        return False

    # الفلترة الجغرافية
    return point_in_polygon(
        lat,
        lon
    )


# ============================================================
# 🕒 قراءة وقت FIRMS
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

        year, month, day = map(
            int,
            date_value.split("-")
        )

        return datetime.datetime(
            year,
            month,
            day,
            hour,
            minute,
            tzinfo=UTC
        )

    except Exception:

        return None


# ============================================================
# 🎯 Confidence
# ============================================================

def confidence_score(value):

    value = str(
        value or ""
    ).strip().lower()

    if value in (
        "h",
        "high"
    ):
        return 90

    if value in (
        "n",
        "nominal"
    ):
        return 65

    if value in (
        "l",
        "low"
    ):
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
# 🔥 نوع النقطة
# ============================================================

def is_natural_fire(row):

    value = row.get(
        "type"
    )

    if value in (
        None,
        ""
    ):
        return True

    try:

        fire_type = int(
            float(value)
        )

        # 0 = vegetation fire
        # 1 = volcano
        # 2 = static land source
        # 3 = offshore
        return fire_type == 0

    except Exception:

        return True


# ============================================================
# 📐 Haversine
# ============================================================

def distance_km(
    lat1,
    lon1,
    lat2,
    lon2
):

    earth_radius = 6371.0

    rlat1 = math.radians(
        lat1
    )

    rlat2 = math.radians(
        lat2
    )

    dlat = (
        rlat2 - rlat1
    )

    dlon = math.radians(
        lon2 - lon1
    )

    a = (
        math.sin(dlat / 2) ** 2
        +
        math.cos(rlat1)
        *
        math.cos(rlat2)
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
            math.sqrt(
                1 - a
            )
        )
    )


# ============================================================
# 🧹 Normalize
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

        if not is_saudi(
            lat,
            lon
        ):
            continue

        if not is_natural_fire(
            row
        ):
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
                row.get(
                    "frp",
                    0
                )
            )

        except Exception:

            frp = 0

        if frp < MIN_FRP:
            continue

        confidence = confidence_score(
            row.get(
                "confidence"
            )
        )

        events.append(
            {
                "lat": lat,
                "lon": lon,
                "frp": frp,
                "confidence": confidence,
                "date": row.get(
                    "acq_date"
                ),
                "time": row.get(
                    "acq_time"
                ),
                "datetime": acquisition,
                "age_hours": age_hours,
                "source": row.get(
                    "satellite",
                    ""
                )
            }
        )

    return events


# ============================================================
# 🔁 إزالة التكرار
# ============================================================

def remove_duplicates(events):

    unique = {}

    for event in events:

        key = (
            round(
                event["lat"],
                3
            ),
            round(
                event["lon"],
                3
            ),
            event["date"],
            event["time"]
        )

        if key not in unique:

            unique[key] = event

        else:

            if (
                event["frp"]
                >
                unique[key]["frp"]
            ):

                unique[key] = event

    return list(
        unique.values()
    )


# ============================================================
# 🔥 Clustering
# ============================================================

def cluster_events(events):

    clusters = []

    events = sorted(
        events,
        key=lambda x: (
            x["frp"],
            x["confidence"]
        ),
        reverse=True
    )

    for event in events:

        assigned = False

        for cluster in clusters:

            center = cluster[
                "center"
            ]

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

                cluster[
                    "events"
                ].append(
                    event
                )

                cluster[
                    "total_frp"
                ] += event["frp"]

                cluster[
                    "max_frp"
                ] = max(
                    cluster["max_frp"],
                    event["frp"]
                )

                cluster[
                    "latest"
                ] = max(
                    cluster["latest"],
                    event["datetime"]
                )

                count = len(
                    cluster["events"]
                )

                cluster[
                    "center"
                ]["lat"] = (
                    sum(
                        e["lat"]
                        for e
                        in cluster[
                            "events"
                        ]
                    ) / count
                )

                cluster[
                    "center"
                ]["lon"] = (
                    sum(
                        e["lon"]
                        for e
                        in cluster[
                            "events"
                        ]
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
                    "events": [
                        event
                    ],
                    "total_frp": event["frp"],
                    "max_frp": event["frp"],
                    "latest": event["datetime"]
                }
            )

    return clusters


# ============================================================
# 🤖 AI Risk Engine
# ============================================================

def calculate_risk(cluster):

    events = cluster[
        "events"
    ]

    count = len(
        events
    )

    max_frp = cluster[
        "max_frp"
    ]

    total_frp = cluster[
        "total_frp"
    ]

    avg_confidence = (
        sum(
            e["confidence"]
            for e in events
        )
        /
        count
    )

    # --------------------------------------------------------
    # FRP
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # عدد النقاط
    # --------------------------------------------------------

    if count >= 10:
        cluster_score = 100

    elif count >= 6:
        cluster_score = 90

    elif count >= 4:
        cluster_score = 80

    elif count >= 3:
        cluster_score = 70

    elif count >= 2:
        cluster_score = 55

    else:
        cluster_score = 20

    # --------------------------------------------------------
    # حداثة البيانات
    # --------------------------------------------------------

    latest_age = min(
        e["age_hours"]
        for e in events
    )

    if latest_age <= 1:
        freshness_score = 100

    elif latest_age <= 3:
        freshness_score = 90

    elif latest_age <= 6:
        freshness_score = 75

    elif latest_age <= 12:
        freshness_score = 60

    else:
        freshness_score = 40

    # --------------------------------------------------------
    # AI Score
    # --------------------------------------------------------

    risk = (
        frp_score * 0.40
        +
        cluster_score * 0.30
        +
        avg_confidence * 0.20
        +
        freshness_score * 0.10
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

    elif risk >= 45:

        level = "متوسط"
        emoji = "🟡"

    else:

        level = "منخفض"
        emoji = "🟢"

    # --------------------------------------------------------
    # تفسير ذكي
    # --------------------------------------------------------

    if (
        count >= 4
        and
        max_frp >= 70
    ):

        assessment = (
            "بؤرة حرارية قوية ومتجمعة "
            "وتستحق المتابعة العاجلة"
        )

    elif count >= 3:

        assessment = (
            "تجمع حراري متعدد النقاط "
            "ويستحق المتابعة"
        )

    elif max_frp >= 100:

        assessment = (
            "نقطة حرارية عالية الشدة "
            "وتحتاج للتحقق والمتابعة"
        )

    elif max_frp >= 50:

        assessment = (
            "نشاط حراري ملحوظ "
            "ويحتاج إلى المراقبة"
        )

    else:

        assessment = (
            "نشاط حراري محدود "
            "مع حاجة للمراقبة"
        )

    return {
        "score": risk,
        "level": level,
        "emoji": emoji,
        "confidence": round(
            avg_confidence
        ),
        "max_frp": max_frp,
        "total_frp": total_frp,
        "count": count,
        "freshness": round(
            freshness_score
        ),
        "assessment": assessment
    }


# ============================================================
# 🆔 Cluster ID
# ============================================================

def cluster_id(cluster):

    lat = round(
        cluster[
            "center"
        ]["lat"],
        2
    )

    lon = round(
        cluster[
            "center"
        ]["lon"],
        2
    )

    latest = cluster[
        "latest"
    ].strftime(
        "%Y-%m-%d-%H"
    )

    return (
        f"{lat}_{lon}_{latest}"
    )


# ============================================================
# 🗺️ Google Maps
# ============================================================

def google_maps(
    lat,
    lon
):

    return (
        "https://www.google.com/maps"
        f"?q={lat},{lon}"
    )


# ============================================================
# 🇸🇦 المنطقة التقريبية
# ============================================================

def approximate_region(
    lat,
    lon
):

    if lat >= 28:
        return "شمال المملكة"

    if lat >= 24 and lon < 44:
        return "المدينة المنورة / شمال غرب المملكة"

    if lat >= 22 and lon < 48:
        return "الرياض / وسط المملكة"

    if lat < 22 and lon < 44:
        return "جازان / جنوب غرب المملكة"

    if lon >= 48:
        return "المنطقة الشرقية"

    return "المملكة العربية السعودية"


# ============================================================
# 🟢 تقرير طبيعي
# ============================================================

def send_no_fire_report(
    raw_count,
    analyzed_count
):

    message = f"""
🟢 رصد حرائق السعودية — V5 AI

🕒 {now_ksa()}

✅ لا توجد بؤر حرائق تستدعي التنبيه حالياً.

📊 بيانات FIRMS المستلمة: {raw_count}
🧪 النقاط بعد التحليل: {analyzed_count}
🚨 البؤر المستوفية لمعايير التنبيه: 0

🛰️ المصدر:
NASA FIRMS / VIIRS

🤖 محرك التحليل:
V5.1 Intelligent Fire Intelligence Engine

📡 الحالة:
النظام يعمل بشكل طبيعي
"""

    tg_send(
        message.strip()
    )


# ============================================================
# 🚨 تقرير الحريق
# ============================================================

def send_fire_report(
    clusters,
    raw_count,
    analyzed_count
):

    clusters = sorted(
        clusters,
        key=lambda c: (
            c["risk"]["score"],
            c["risk"]["max_frp"],
            c["risk"]["count"]
        ),
        reverse=True
    )

    top = clusters[
        :TOP_CLUSTERS
    ]

    highest = top[0]

    lat = highest[
        "center"
    ]["lat"]

    lon = highest[
        "center"
    ]["lon"]

    risk = highest[
        "risk"
    ]

    region = approximate_region(
        lat,
        lon
    )

    message = []

    message.append(
        "🔥 تنبيه حرائق السعودية — V5 AI"
    )

    message.append(
        f"🕒 {now_ksa()}"
    )

    message.append("")

    message.append(
        f"🚨 البؤر التي تستدعي المتابعة: "
        f"{len(clusters)}"
    )

    message.append(
        f"📊 النقاط الحرارية المحللة: "
        f"{analyzed_count}"
    )

    message.append("")

    message.append(
        "⚠️ أعلى مستوى خطورة:"
    )

    message.append(
        f"{risk['emoji']} "
        f"{risk['level']} "
        f"— {risk['score']}/100"
    )

    message.append("")

    message.append(
        "🤖 التقييم الذكي:"
    )

    message.append(
        risk["assessment"]
    )

    message.append("")

    message.append(
        "📌 أبرز البؤر:"
    )

    for index, cluster in enumerate(
        top,
        start=1
    ):

        c = cluster[
            "center"
        ]

        r = cluster[
            "risk"
        ]

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
📍 الموقع: {c['lat']:.4f}, {c['lon']:.4f}
🗺️ النطاق: {region_name}
🔥 عدد النقاط: {r['count']}
⚡ أعلى شدة: {r['max_frp']:.1f} MW
📊 إجمالي FRP: {r['total_frp']:.1f} MW
🎯 الثقة: {confidence}
🤖 التقييم: {r['assessment']}
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
        "V5.1 Intelligent Fire Intelligence Engine"
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

    print("=" * 65)

    print(
        "🔥 Saudi Wildfire Intelligence V5.1 AI"
    )

    print(
        f"🕒 {now_ksa()}"
    )

    print("=" * 65)

    state = load_state()

    seen = state.get(
        "seen",
        {}
    )

    all_rows = []

    # ========================================================
    # قراءة الأقمار
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
        f"🧪 After Saudi + AI filtering: "
        f"{len(events)}"
    )

    # ========================================================
    # إزالة التكرار
    # ========================================================

    events = remove_duplicates(
        events
    )

    print(
        f"🔁 After duplicates: "
        f"{len(events)}"
    )

    # ========================================================
    # تسجيل الأحداث الجديدة
    # ========================================================

    new_events = []

    for event in events:

        uid = (
            f"{round(event['lat'], 3)}_"
            f"{round(event['lon'], 3)}_"
            f"{event['date']}_"
            f"{event['time']}"
        )

        if uid not in seen:

            seen[uid] = (
                now_utc().isoformat()
            )

            new_events.append(
                event
            )

    print(
        f"🆕 New events: "
        f"{len(new_events)}"
    )

    # ========================================================
    # Clustering
    # ========================================================

    clusters = cluster_events(
        events
    )

    print(
        f"🔥 Clusters: "
        f"{len(clusters)}"
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
    # Alert filtering
    # ========================================================

    alert_clusters = []

    for cluster in valid_clusters:

        risk = cluster[
            "risk"
        ]

        count = risk[
            "count"
        ]

        score = risk[
            "score"
        ]

        max_frp = risk[
            "max_frp"
        ]

        # ----------------------------------------------------
        # بؤرة متعددة النقاط
        # ----------------------------------------------------

        if count >= 2:

            if score >= MIN_ALERT_SCORE:

                alert_clusters.append(
                    cluster
                )

        # ----------------------------------------------------
        # نقطة واحدة
        # ----------------------------------------------------

        else:

            if (
                score
                >=
                SINGLE_POINT_MIN_SCORE
                and
                max_frp >= 50
            ):

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

        if SEND_NORMAL_STATUS:

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
    # حفظ الحالة
    # ========================================================

    state["seen"] = seen

    save_state(
        state
    )

    print(
        "✅ V5.1 AI completed successfully"
    )


# ============================================================
# تشغيل النظام
# ============================================================

if __name__ == "__main__":

    main()
