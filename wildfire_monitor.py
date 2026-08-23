import os
import json
import math
import datetime
import time
import requests

# ============================================================
# 🔥 Saudi Wildfire Intelligence V5.6
# Advanced Geographic + Verification Intelligence Engine
#
# NASA FIRMS + VIIRS
#
# V5.6:
# - Saudi Arabia Polygon Validation
# - VIIRS SNPP + NOAA-20
# - Intelligent Clustering
# - Risk Score
# - Verification Score
# - Persistence Score
# - FRP Escalation
# - Cluster Growth Detection
# - Trend Analysis
# - Duplicate Protection
# - State Memory
# - Smart Classification
# - Smart Recommendation
# - Arabic Telegram Alerts
# ============================================================


# ============================================================
# ENVIRONMENT
# ============================================================

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
FIRMS_KEY = os.environ["FIRMS_API_KEY"]

KSA_TZ = datetime.timezone(
    datetime.timedelta(hours=3)
)

STATE_FILE = "wildfire_state_v56.json"


# ============================================================
# 🇸🇦 SAUDI BOUNDING BOX
# ============================================================

BBOX = (
    34.5,   # min longitude
    16.0,   # min latitude
    55.8,   # max longitude
    32.6    # max latitude
)


# ============================================================
# SATELLITE SOURCES
# ============================================================

SOURCES = [
    "VIIRS_SNPP_NRT",
    "VIIRS_NOAA20_NRT",
]


# ============================================================
# ANALYSIS SETTINGS
# ============================================================

MIN_FRP = 3.0

MAX_AGE_HOURS = 24

CLUSTER_RADIUS_KM = 2.5

CLUSTER_TIME_MINUTES = 180

TOP_CLUSTERS = 5


# ============================================================
# ALERT SETTINGS
# ============================================================

ALERT_THRESHOLD = 40

RISK_CHANGE_ALERT = 8

FRP_CHANGE_ALERT = 25

COUNT_CHANGE_ALERT = 2

CLUSTER_MEMORY_HOURS = 72

ALERT_NEW_CLUSTER = True


# ============================================================
# HTTP
# ============================================================

HTTP_HEADERS = {
    "User-Agent":
        "Saudi-Wildfire-Intelligence-V5.6",
    "Accept":
        "text/csv,*/*",
    "Connection":
        "close",
}


# ============================================================
# 🇸🇦 SAUDI ARABIA POLYGON
# ============================================================

SAUDI_POLYGON = [
    (42.779332, 16.347891),
    (42.649573, 16.774635),
    (42.347989, 17.075806),
    (42.270888, 17.474722),
    (41.754382, 17.833046),
    (41.221391, 18.671600),
    (40.939341, 19.486485),
    (40.247652, 20.174635),
    (39.801685, 20.338862),
    (39.139399, 21.291905),
    (39.023696, 21.986875),
    (39.066329, 22.579656),
    (38.492772, 23.688451),
    (38.023860, 24.078686),
    (37.483635, 24.285495),
    (37.154818, 24.858483),
    (37.209491, 25.084542),
    (36.931627, 25.602959),
    (36.639604, 25.826228),
    (36.249137, 26.570136),
    (35.640182, 27.376520),
    (35.130187, 28.063352),
    (34.632336, 28.058546),
    (34.787779, 28.607427),
    (34.832220, 28.957483),
    (34.956037, 29.356555),
    (36.068941, 29.197495),
    (36.501214, 29.505254),
    (36.740528, 29.865283),
    (37.503582, 30.003776),
    (37.668120, 30.338665),
    (37.998849, 30.508500),
    (37.002166, 31.508413),
    (39.004886, 32.010217),
    (39.195468, 32.161009),
    (40.399994, 31.889992),
    (41.889981, 31.190009),
    (44.709499, 29.178891),
    (46.568713, 29.099025),
    (47.459822, 29.002519),
    (47.708851, 28.526063),
    (48.416094, 28.552004),
    (48.807595, 27.689628),
    (49.299554, 27.461218),
    (49.470914, 27.109999),
    (50.152422, 26.689663),
    (50.212935, 26.277027),
    (50.113303, 25.943972),
    (50.239859, 25.608050),
    (50.527387, 25.327808),
    (50.660557, 24.999896),
    (50.810108, 24.754743),
    (51.112415, 24.556331),
    (51.389608, 24.627386),
    (51.579519, 24.245497),
    (51.617708, 24.014219),
    (52.000733, 23.001154),
    (55.006803, 22.496948),
    (55.208341, 22.708330),
    (55.666659, 22.000001),
    (54.999982, 19.999994),
    (52.000010, 19.000003),
    (49.116672, 18.616668),
    (48.183344, 18.166669),
    (47.466695, 17.116682),
    (47.000005, 16.949999),
    (46.749994, 17.283338),
    (46.366659, 17.233315),
    (45.399999, 17.333335),
    (45.216651, 17.433329),
    (44.062613, 17.410359),
    (43.791519, 17.319977),
    (43.380794, 17.579987),
    (43.115798, 17.088440),
    (43.218375, 16.666890),
]


# ============================================================
# TIME
# ============================================================

def now_utc():
    return datetime.datetime.now(
        datetime.timezone.utc
    )


def now_ksa():
    return datetime.datetime.now(
        KSA_TZ
    ).strftime(
        "%Y-%m-%d %H:%M KSA"
    )


# ============================================================
# STATE
# ============================================================

def default_state():
    return {
        "seen": {},
        "clusters": {},
        "last_run": None
    }


def load_state():

    if not os.path.exists(STATE_FILE):
        return default_state()

    try:

        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            state = json.load(f)

        if not isinstance(state, dict):
            return default_state()

        state.setdefault("seen", {})
        state.setdefault("clusters", {})
        state.setdefault("last_run", None)

        return state

    except Exception as e:

        print(
            f"⚠️ State load error: {e}"
        )

        return default_state()


def save_state(state):

    cutoff = (
        now_utc()
        -
        datetime.timedelta(
            hours=CLUSTER_MEMORY_HOURS
        )
    )

    # --------------------------------------------------------
    # CLEAN SEEN
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # CLEAN CLUSTERS
    # --------------------------------------------------------

    cleaned_clusters = {}

    for key, value in state.get(
        "clusters",
        {}
    ).items():

        try:

            dt = datetime.datetime.fromisoformat(
                value.get(
                    "last_seen"
                )
            )

            if dt >= cutoff:
                cleaned_clusters[key] = value

        except Exception:
            pass

    state["clusters"] = cleaned_clusters

    state["last_run"] = now_utc().isoformat()

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
# TELEGRAM
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

    print(
        "📨 Telegram alert sent"
    )


# ============================================================
# CSV PARSER
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

        rows.append({
            header[i]: columns[i]
            for i in range(len(header))
        })

    return rows


# ============================================================
# FIRMS
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
        "api/area/csv/"
        f"{FIRMS_KEY}/"
        f"{source}/"
        f"{bbox}/1"
    )

    last_error = None

    for attempt in range(3):

        try:

            print(
                f"   🔄 محاولة الاتصال "
                f"{attempt + 1}/3"
            )

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
        f"❌ FIRMS API error "
        f"({source}): {last_error}"
    )

    return []


# ============================================================
# POINT IN POLYGON
# ============================================================

def point_in_polygon(
    lat,
    lon,
    polygon
):

    inside = False

    x = lon
    y = lat

    j = len(polygon) - 1

    for i in range(
        len(polygon)
    ):

        xi, yi = polygon[i]
        xj, yj = polygon[j]

        denominator = (
            yj - yi
        )

        if denominator == 0:
            j = i
            continue

        intersects = (
            (
                yi > y
            )
            !=
            (
                yj > y
            )
        ) and (
            x
            <
            (
                (xj - xi)
                *
                (y - yi)
                /
                denominator
            )
            +
            xi
        )

        if intersects:
            inside = not inside

        j = i

    return inside


def is_inside_saudi(
    lat,
    lon
):

    min_lon, min_lat, max_lon, max_lat = BBOX

    if not (
        min_lat <= lat <= max_lat
        and
        min_lon <= lon <= max_lon
    ):
        return False

    return point_in_polygon(
        lat,
        lon,
        SAUDI_POLYGON
    )


# ============================================================
# DATETIME
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
        ).strip().zfill(4)

        hour = int(
            time_value[:2]
        )

        minute = int(
            time_value[2:4]
        )

        if (
            hour > 23
            or
            minute > 59
        ):
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
            tzinfo=datetime.timezone.utc
        )

    except Exception:

        return None


# ============================================================
# CONFIDENCE
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
# HAVERSINE
# ============================================================

def distance_km(
    lat1,
    lon1,
    lat2,
    lon2
):

    earth_radius = 6371.0

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)

    dlat = (
        lat2_rad
        -
        lat1_rad
    )

    dlon = math.radians(
        lon2 - lon1
    )

    a = (
        math.sin(
            dlat / 2
        ) ** 2
        +
        math.cos(lat1_rad)
        *
        math.cos(lat2_rad)
        *
        math.sin(
            dlon / 2
        ) ** 2
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
# NATURAL FIRE
# ============================================================

def is_natural_fire(row):

    value = row.get("type")

    if value in (
        None,
        ""
    ):
        return True

    try:

        fire_type = int(
            float(value)
        )

        return fire_type == 0

    except Exception:

        return True


# ============================================================
# NORMALIZE
# ============================================================

def normalize_rows(rows):

    events = []

    current_time = now_utc()

    outside_bbox = 0
    outside_saudi = 0
    invalid_coordinates = 0
    old_events = 0
    low_frp = 0
    non_natural = 0

    for row in rows:

        try:

            lat = float(
                row["latitude"]
            )

            lon = float(
                row["longitude"]
            )

        except Exception:

            invalid_coordinates += 1
            continue

        # ----------------------------------------------------
        # BBOX
        # ----------------------------------------------------

        min_lon, min_lat, max_lon, max_lat = BBOX

        if not (
            min_lat <= lat <= max_lat
            and
            min_lon <= lon <= max_lon
        ):

            outside_bbox += 1
            continue

        # ----------------------------------------------------
        # POLYGON
        # ----------------------------------------------------

        if not is_inside_saudi(
            lat,
            lon
        ):

            outside_saudi += 1
            continue

        # ----------------------------------------------------
        # NATURAL FIRE
        # ----------------------------------------------------

        if not is_natural_fire(row):

            non_natural += 1
            continue

        # ----------------------------------------------------
        # DATETIME
        # ----------------------------------------------------

        acquisition = (
            parse_acquisition_datetime(
                row.get("acq_date"),
                row.get("acq_time")
            )
        )

        if acquisition is None:
            continue

        age_hours = (
            current_time
            -
            acquisition
        ).total_seconds() / 3600

        if age_hours < 0:
            age_hours = 0

        if age_hours > MAX_AGE_HOURS:

            old_events += 1
            continue

        # ----------------------------------------------------
        # FRP
        # ----------------------------------------------------

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

            low_frp += 1
            continue

        confidence = confidence_score(
            row.get("confidence")
        )

        events.append({

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

            "age_hours": age_hours

        })

    stats = {

        "outside_bbox":
            outside_bbox,

        "outside_saudi":
            outside_saudi,

        "invalid_coordinates":
            invalid_coordinates,

        "old_events":
            old_events,

        "low_frp":
            low_frp,

        "non_natural":
            non_natural

    }

    return events, stats


# ============================================================
# DUPLICATES
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

        elif (
            event["frp"]
            >
            unique[key]["frp"]
        ):

            unique[key] = event

    return list(
        unique.values()
    )


# ============================================================
# CLUSTERING
# ============================================================

def cluster_events(events):

    clusters = []

    events = sorted(
        events,
        key=lambda x:
            x["frp"],
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
                distance <= CLUSTER_RADIUS_KM
                and
                time_difference <= CLUSTER_TIME_MINUTES
            ):

                cluster[
                    "events"
                ].append(event)

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
                        for e in
                        cluster["events"]
                    )
                    /
                    count
                )

                cluster[
                    "center"
                ]["lon"] = (
                    sum(
                        e["lon"]
                        for e in
                        cluster["events"]
                    )
                    /
                    count
                )

                assigned = True
                break

        if not assigned:

            clusters.append({

                "center": {

                    "lat":
                        event["lat"],

                    "lon":
                        event["lon"]

                },

                "events":
                    [event],

                "total_frp":
                    event["frp"],

                "max_frp":
                    event["frp"],

                "latest":
                    event["datetime"]

            })

    return clusters


# ============================================================
# FRP SCORE
# ============================================================

def frp_score(max_frp):

    if max_frp >= 150:
        return 100

    if max_frp >= 100:
        return 90

    if max_frp >= 70:
        return 80

    if max_frp >= 40:
        return 65

    if max_frp >= 20:
        return 50

    if max_frp >= 10:
        return 35

    return 20


# ============================================================
# CLUSTER SCORE
# ============================================================

def cluster_score(count):

    if count >= 10:
        return 100

    if count >= 7:
        return 90

    if count >= 5:
        return 80

    if count >= 3:
        return 70

    if count >= 2:
        return 50

    return 20


# ============================================================
# RISK ENGINE
# ============================================================

def calculate_risk(cluster):

    count = len(
        cluster["events"]
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
            for e in cluster["events"]
        )
        /
        count
    )

    f_score = frp_score(
        max_frp
    )

    c_score = cluster_score(
        count
    )

    # --------------------------------------------------------
    # CURRENT PERSISTENCE
    # --------------------------------------------------------

    if count >= 5:
        persistence = 80

    elif count >= 3:
        persistence = 60

    elif count >= 2:
        persistence = 40

    else:
        persistence = 20

    # --------------------------------------------------------
    # BASE RISK
    # --------------------------------------------------------

    risk = (

        f_score * 0.40

        +

        c_score * 0.30

        +

        avg_confidence * 0.20

        +

        persistence * 0.10

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

        "score":
            risk,

        "level":
            level,

        "emoji":
            emoji,

        "confidence":
            round(
                avg_confidence
            ),

        "max_frp":
            max_frp,

        "total_frp":
            total_frp,

        "count":
            count

    }


# ============================================================
# PERSISTENCE SCORE
# ============================================================

def calculate_persistence(
    current,
    previous
):

    if previous is None:
        return 20

    old_count = int(
        previous.get(
            "count",
            1
        )
    )

    current_count = len(
        current["events"]
    )

    old_frp = float(
        previous.get(
            "max_frp",
            0
        )
    )

    current_frp = float(
        current["max_frp"]
    )

    score = 20

    if old_count >= 2:
        score += 20

    if current_count >= old_count:
        score += 20

    if current_frp >= old_frp:
        score += 20

    if current_count >= 5:
        score += 10

    if current_frp >= 70:
        score += 10

    return min(
        100,
        score
    )


# ============================================================
# ADVANCED RISK
# ============================================================

def calculate_advanced_risk(
    cluster,
    previous
):

    base = calculate_risk(
        cluster
    )

    count = base[
        "count"
    ]

    max_frp = base[
        "max_frp"
    ]

    confidence = base[
        "confidence"
    ]

    persistence = calculate_persistence(
        cluster,
        previous
    )

    f_score = frp_score(
        max_frp
    )

    c_score = cluster_score(
        count
    )

    score = (

        f_score * 0.38

        +

        c_score * 0.27

        +

        confidence * 0.20

        +

        persistence * 0.15

    )

    score = round(
        min(
            100,
            max(
                0,
                score
            )
        )
    )

    if score >= 80:

        level = "حرج"
        emoji = "🔴"

    elif score >= 60:

        level = "مرتفع"
        emoji = "🟠"

    elif score >= 40:

        level = "متوسط"
        emoji = "🟡"

    else:

        level = "منخفض"
        emoji = "🟢"

    base["score"] = score
    base["level"] = level
    base["emoji"] = emoji
    base["persistence"] = persistence

    return base


# ============================================================
# VERIFICATION SCORE
# ============================================================

def calculate_verification_score(
    cluster,
    previous=None
):

    count = len(
        cluster["events"]
    )

    max_frp = cluster[
        "max_frp"
    ]

    avg_confidence = (
        sum(
            e["confidence"]
            for e in cluster["events"]
        )
        /
        count
    )

    # --------------------------------------------------------
    # CLUSTER COMPONENT
    # --------------------------------------------------------

    if count >= 10:
        cluster_component = 100

    elif count >= 7:
        cluster_component = 90

    elif count >= 5:
        cluster_component = 80

    elif count >= 3:
        cluster_component = 70

    elif count >= 2:
        cluster_component = 50

    else:
        cluster_component = 25

    # --------------------------------------------------------
    # FRP COMPONENT
    # --------------------------------------------------------

    if max_frp >= 150:
        frp_component = 100

    elif max_frp >= 100:
        frp_component = 90

    elif max_frp >= 70:
        frp_component = 80

    elif max_frp >= 40:
        frp_component = 65

    elif max_frp >= 20:
        frp_component = 50

    else:
        frp_component = 30

    # --------------------------------------------------------
    # PERSISTENCE
    # --------------------------------------------------------

    persistence = calculate_persistence(
        cluster,
        previous
    )

    verification = (

        cluster_component * 0.35

        +

        frp_component * 0.30

        +

        avg_confidence * 0.20

        +

        persistence * 0.15

    )

    return round(
        min(
            100,
            max(
                0,
                verification
            )
        )
    )


# ============================================================
# CLASSIFICATION
# ============================================================

def classify_cluster(
    risk,
    verification
):

    score = risk[
        "score"
    ]

    count = risk[
        "count"
    ]

    max_frp = risk[
        "max_frp"
    ]

    if (
        score >= 80
        and
        verification >= 75
        and
        count >= 3
    ):

        return (
            "حريق محتمل عالي الأولوية",
            "بؤرة حرارية قوية ومتجمعة وتستدعي التحقق العاجل"
        )

    if (
        score >= 70
        and
        verification >= 65
        and
        count >= 3
    ):

        return (
            "حريق محتمل مرتفع الأولوية",
            "تجمع حراري قوي متعدد النقاط ويستحق المتابعة المكثفة"
        )

    if (
        score >= 60
        and
        count >= 2
    ):

        return (
            "بؤرة حرارية مرتفعة الأولوية",
            "نشاط حراري متجمع يحتاج إلى متابعة والتحقق"
        )

    if score >= 50:

        return (
            "بؤرة حرارية تحتاج مراقبة",
            "بؤرة حرارية ملحوظة وتحتاج إلى المتابعة"
        )

    if max_frp >= 40:

        return (
            "نقطة حرارية قوية",
            "شدة حرارية مرتفعة ولكن الأدلة غير كافية لتأكيد حريق"
        )

    return (
        "نشاط حراري منخفض الأولوية",
        "نشاط حراري محدود ولا يستدعي تنبيهًا عاجلًا"
    )


# ============================================================
# TREND
# ============================================================

def calculate_trend(
    cluster,
    previous
):

    if not previous:

        return (
            "🆕 جديدة",
            "بؤرة جديدة"
        )

    old_score = float(
        previous.get(
            "risk",
            0
        )
    )

    new_score = cluster[
        "risk"
    ][
        "score"
    ]

    difference = (
        new_score
        -
        old_score
    )

    old_count = int(
        previous.get(
            "count",
            0
        )
    )

    new_count = len(
        cluster["events"]
    )

    if (
        difference >= 8
        or
        new_count - old_count >= COUNT_CHANGE_ALERT
    ):

        return (
            "📈 تصاعد",
            "ارتفاع مستوى النشاط الحراري"
        )

    if difference <= -8:

        return (
            "📉 تراجع",
            "انخفاض مستوى الخطورة"
        )

    return (
        "➡️ مستقر",
        "مستوى النشاط مستقر نسبيًا"
    )


# ============================================================
# RECOMMENDATION
# ============================================================

def recommendation(
    risk,
    verification,
    trend
):

    score = risk[
        "score"
    ]

    count = risk[
        "count"
    ]

    if (
        score >= 80
        and
        verification >= 75
        and
        count >= 3
    ):

        return (
            "🚨 التوصية: متابعة عاجلة "
            "والتحقق من البؤرة ميدانيًا "
            "أو عبر مصدر مرئي إضافي."
        )

    if score >= 70:

        if "تصاعد" in trend:

            return (
                "🚨 التوصية: رفع مستوى المراقبة "
                "والتحقق من استمرار النشاط بشكل عاجل."
            )

        return (
            "⚠️ التوصية: متابعة مكثفة "
            "والتحقق من النشاط."
        )

    if score >= 60:

        return (
            "⚠️ التوصية: متابعة البؤرة "
            "والتحقق من استمرار النشاط."
        )

    if score >= 50:

        return (
            "👁️ التوصية: إبقاء البؤرة "
            "تحت المراقبة."
        )

    return (
        "ℹ️ التوصية: مراقبة روتينية."
    )


# ============================================================
# CLUSTER ID
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

    return (
        f"{lat}_{lon}"
    )


# ============================================================
# REGION
#
# تصنيف جغرافي تقريبي للاستخدام في التقرير فقط.
# التحقق من الدولة يتم بالـPolygon.
# ============================================================

def approximate_region(
    lat,
    lon
):

    # --------------------------------------------------------
    # NORTHERN
    # --------------------------------------------------------

    if lat >= 30:

        if lon < 38:
            return "تبوك"

        if lon < 41:
            return "الجوف"

        if lon < 44:
            return "الحدود الشمالية"

        return "الحدود الشمالية / شرق المملكة"

    # --------------------------------------------------------
    # NORTH CENTRAL
    # --------------------------------------------------------

    if lat >= 28:

        if lon < 39:
            return "تبوك / شمال غرب المملكة"

        if lon < 42:
            return "الجوف / حائل"

        if lon < 45:
            return "حائل"

        if lon < 47:
            return "الحدود الشمالية / حائل"

        return "الحدود الشمالية / شرق المملكة"

    # --------------------------------------------------------
    # CENTRAL
    # --------------------------------------------------------

    if lat >= 25:

        if lon < 39:
            return "المدينة المنورة"

        if lon < 42:
            return "المدينة المنورة / القصيم"

        if lon < 46:
            return "القصيم / الرياض"

        if lon < 49:
            return "الرياض / المنطقة الشرقية"

        return "المنطقة الشرقية"

    # --------------------------------------------------------
    # EAST / WEST
    # --------------------------------------------------------

    if lat >= 22:

        if lon < 40:
            return "مكة المكرمة / المدينة المنورة"

        if lon < 43:
            return "مكة المكرمة / الرياض"

        if lon < 47:
            return "الرياض / وسط المملكة"

        return "المنطقة الشرقية"

    # --------------------------------------------------------
    # SOUTH
    # --------------------------------------------------------

    if lat >= 18:

        if lon < 41:
            return "مكة المكرمة / عسير"

        if lon < 44:
            return "عسير"

        if lon < 47:
            return "نجران"

        return "المنطقة الشرقية / نجران"

    return "جازان / جنوب المملكة"


# ============================================================
# GOOGLE MAPS
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
# ALERT DECISION
# ============================================================

def should_alert_cluster(
    cluster,
    previous
):

    risk = cluster[
        "risk"
    ]

    verification = cluster[
        "verification"
    ]

    if previous is None:

        if not ALERT_NEW_CLUSTER:
            return False

        # لا نرسل نقطة منفردة منخفضة
        if (
            risk["count"] == 1
            and
            risk["score"] < ALERT_THRESHOLD
        ):
            return False

        return True

    old_score = float(
        previous.get(
            "risk",
            0
        )
    )

    old_verification = float(
        previous.get(
            "verification",
            0
        )
    )

    old_frp = float(
        previous.get(
            "max_frp",
            0
        )
    )

    old_count = int(
        previous.get(
            "count",
            0
        )
    )

    new_score = risk[
        "score"
    ]

    new_verification = verification

    new_frp = risk[
        "max_frp"
    ]

    new_count = risk[
        "count"
    ]

    score_difference = (
        new_score
        -
        old_score
    )

    verification_difference = (
        new_verification
        -
        old_verification
    )

    frp_difference = (
        new_frp
        -
        old_frp
    )

    count_difference = (
        new_count
        -
        old_count
    )

    # --------------------------------------------------------
    # RISK ESCALATION
    # --------------------------------------------------------

    if score_difference >= RISK_CHANGE_ALERT:
        return True

    # --------------------------------------------------------
    # LOW → MEDIUM
    # MEDIUM → HIGH
    # HIGH → CRITICAL
    # --------------------------------------------------------

    if (
        old_score < 40
        and
        new_score >= 40
    ):
        return True

    if (
        old_score < 60
        and
        new_score >= 60
    ):
        return True

    if (
        old_score < 80
        and
        new_score >= 80
    ):
        return True

    # --------------------------------------------------------
    # VERIFICATION IMPROVEMENT
    # --------------------------------------------------------

    if verification_difference >= 15:
        return True

    # --------------------------------------------------------
    # FRP ESCALATION
    # --------------------------------------------------------

    if (
        old_frp > 0
        and
        frp_difference >= FRP_CHANGE_ALERT
    ):
        return True

    # --------------------------------------------------------
    # CLUSTER GROWTH
    # --------------------------------------------------------

    if count_difference >= COUNT_CHANGE_ALERT:
        return True

    return False


# ============================================================
# NO FIRE REPORT
# ============================================================

def send_no_fire_report(
    raw_count,
    normalized_count,
    outside_saudi
):

    message = f"""

🟢 رصد حرائق السعودية — V5.6 AI

🕒 {now_ksa()}

✅ لا توجد بؤر تستدعي التنبيه العاجل حاليًا.

📊 بيانات FIRMS المستلمة:
{raw_count}

🧪 النقاط بعد التحليل:
{normalized_count}

🇸🇦 نقاط مستبعدة خارج حدود المملكة:
{outside_saudi}

🛰️ المصدر:
NASA FIRMS / VIIRS

🤖 محرك التحليل:
V5.6 Advanced Geographic & Verification Engine

🇸🇦 التحقق الجغرافي:
Saudi Arabia Boundary Polygon

⚠️ المخرجات تمثل بؤرًا حرارية وليست تأكيدًا ميدانيًا للحريق.

الحالة:
النظام يعمل بشكل طبيعي

""".strip()

    tg_send(
        message
    )


# ============================================================
# FIRE REPORT
# ============================================================

def send_fire_report(
    clusters,
    raw_count,
    normalized_count,
    outside_saudi
):

    clusters = sorted(

        clusters,

        key=lambda c: (

            c["risk"]["score"],

            c["verification"],

            c["risk"]["max_frp"],

            c["risk"]["count"]

        ),

        reverse=True
    )

    top = clusters[
        :TOP_CLUSTERS
    ]

    highest = top[0]

    highest_risk = highest[
        "risk"
    ]

    highest_verification = highest[
        "verification"
    ]

    highest_lat = highest[
        "center"
    ][
        "lat"
    ]

    highest_lon = highest[
        "center"
    ][
        "lon"
    ]

    _, explanation = classify_cluster(
        highest_risk,
        highest_verification
    )

    message = []

    message.append(
        "🔥 تنبيه حرائق السعودية — V5.6 AI"
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
        f"{normalized_count}"
    )

    message.append(
        f"🇸🇦 النقاط المستبعدة خارج حدود المملكة: "
        f"{outside_saudi}"
    )

    message.append("")

    message.append(
        "⚠️ أعلى مستوى خطورة:"
    )

    message.append(
        f"{highest_risk['emoji']} "
        f"{highest_risk['level']} — "
        f"{highest_risk['score']}/100"
    )

    message.append("")

    message.append(
        "🧠 درجة التحقق الذكي:"
    )

    message.append(
        f"{highest_verification}/100"
    )

    message.append("")

    message.append(
        "🤖 التقييم الذكي:"
    )

    message.append(
        explanation
    )

    message.append("")

    message.append(
        "📌 أبرز البؤر:"
    )

    for index, cluster in enumerate(
        top,
        start=1
    ):

        center = cluster[
            "center"
        ]

        risk = cluster[
            "risk"
        ]

        verification = cluster[
            "verification"
        ]

        lat = center[
            "lat"
        ]

        lon = center[
            "lon"
        ]

        region = approximate_region(
            lat,
            lon
        )

        classification, explanation = (
            classify_cluster(
                risk,
                verification
            )
        )

        trend_text = cluster.get(
            "trend",
            "➡️ مستقر"
        )

        trend_description = cluster.get(
            "trend_description",
            "مستوى النشاط مستقر نسبيًا"
        )

        rec = recommendation(
            risk,
            verification,
            trend_text
        )

        message.append("")

        message.append(
            f"{index}) "
            f"{risk['emoji']} "
            f"{risk['level']} — "
            f"{risk['score']}/100"
        )

        message.append(
            f"📍 الموقع: "
            f"{lat:.4f}, {lon:.4f}"
        )

        message.append(
            f"🗺️ النطاق: "
            f"{region}"
        )

        message.append(
            f"🔥 عدد النقاط: "
            f"{risk['count']}"
        )

        message.append(
            f"⚡ أعلى شدة: "
            f"{risk['max_frp']:.1f} MW"
        )

        message.append(
            f"📊 إجمالي FRP: "
            f"{risk['total_frp']:.1f} MW"
        )

        message.append(
            f"🎯 الثقة: "
            f"{confidence_ar(risk['confidence'])}"
        )

        message.append(
            f"🤖 التقييم: "
            f"{classification}"
        )

        message.append(
            f"📈 الاتجاه: "
            f"{trend_text}"
        )

        message.append(
            f"🔄 الحالة: "
            f"{trend_text} — "
            f"{trend_description}"
        )

        message.append(
            f"🧠 درجة التحقق: "
            f"{verification}/100"
        )

        message.append(
            f"🧠 الاستمرارية: "
            f"{risk.get('persistence', 0)}/100"
        )

        message.append(
            f"🧠 التحليل: "
            f"{explanation}"
        )

        message.append(
            rec
        )

    message.append("")

    message.append(
        "📍 موقع أعلى بؤرة:"
    )

    message.append(
        google_maps(
            highest_lat,
            highest_lon
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
        "V5.6 Advanced Geographic & Verification Engine"
    )

    message.append("")

    message.append(
        "🇸🇦 التحقق الجغرافي:"
    )

    message.append(
        "Saudi Arabia Boundary Polygon"
    )

    message.append("")

    message.append(
        "⚠️ ملاحظة: "
        "المخرجات تمثل بؤرًا حرارية وحريقًا محتملًا "
        "وليست تأكيدًا ميدانيًا للحريق."
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

    print(
        "=" * 70
    )

    print(
        "🔥 Saudi Wildfire Intelligence V5.6"
    )

    print(
        f"🕒 {now_ksa()}"
    )

    print(
        "🇸🇦 Saudi Polygon Validation ENABLED"
    )

    print(
        "🧠 Advanced Verification ENABLED"
    )

    print(
        "📈 Persistence & Escalation ENABLED"
    )

    print(
        "=" * 70
    )

    state = load_state()

    seen = state.get(
        "seen",
        {}
    )

    previous_clusters = state.get(
        "clusters",
        {}
    )

    all_rows = []

    # ========================================================
    # FIRMS
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
        f"📊 Total FIRMS rows: "
        f"{raw_count}"
    )

    # ========================================================
    # NORMALIZE
    # ========================================================

    events, stats = normalize_rows(
        all_rows
    )

    print(
        f"🧪 After Saudi filtering: "
        f"{len(events)}"
    )

    print(
        f"🇸🇦 Outside Saudi Polygon: "
        f"{stats['outside_saudi']}"
    )

    print(
        f"🗑️ Old events: "
        f"{stats['old_events']}"
    )

    print(
        f"🔥 Low FRP removed: "
        f"{stats['low_frp']}"
    )

    print(
        f"🌿 Non-natural removed: "
        f"{stats['non_natural']}"
    )

    # ========================================================
    # DUPLICATES
    # ========================================================

    events = remove_duplicates(
        events
    )

    print(
        f"🔁 After duplicates: "
        f"{len(events)}"
    )

    # ========================================================
    # NEW EVENTS
    #
    # مهم:
    # تسجيل الحدث يتم بعد نجاح التحليل الأساسي.
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

        new_events.append(
            event
        )

        seen[uid] = (
            now_utc().isoformat()
        )

    print(
        f"🆕 New events: "
        f"{len(new_events)}"
    )

    # ========================================================
    # CLUSTER
    # ========================================================

    clusters = cluster_events(
        events
    )

    print(
        f"🔥 Clusters: "
        f"{len(clusters)}"
    )

    # ========================================================
    # RISK + VERIFICATION + TREND
    # ========================================================

    alert_clusters = []

    current_cluster_state = {}

    for cluster in clusters:

        cid = cluster_id(
            cluster
        )

        previous = previous_clusters.get(
            cid
        )

        # ----------------------------------------------------
        # ADVANCED RISK
        # ----------------------------------------------------

        risk = calculate_advanced_risk(
            cluster,
            previous
        )

        # ----------------------------------------------------
        # VERIFICATION
        # ----------------------------------------------------

        verification = (
            calculate_verification_score(
                cluster,
                previous
            )
        )

        cluster["risk"] = risk

        cluster[
            "verification"
        ] = verification

        # ----------------------------------------------------
        # TREND
        # ----------------------------------------------------

        trend, trend_description = (
            calculate_trend(
                cluster,
                previous
            )
        )

        cluster[
            "trend"
        ] = trend

        cluster[
            "trend_description"
        ] = trend_description

        # ----------------------------------------------------
        # CURRENT STATE
        # ----------------------------------------------------

        current_cluster_state[
            cid
        ] = {

            "risk":
                risk["score"],

            "verification":
                verification,

            "lat":
                cluster["center"]["lat"],

            "lon":
                cluster["center"]["lon"],

            "count":
                risk["count"],

            "max_frp":
                risk["max_frp"],

            "total_frp":
                risk["total_frp"],

            "last_seen":
                now_utc().isoformat()

        }

        # ----------------------------------------------------
        # IGNORE VERY LOW SINGLE POINTS
        # ----------------------------------------------------

        if (
            risk["score"] < ALERT_THRESHOLD
            and
            risk["count"] == 1
        ):

            print(
                f"🟢 Low cluster ignored: "
                f"{cid} "
                f"{risk['score']}/100"
            )

            continue

        # ----------------------------------------------------
        # ALERT DECISION
        # ----------------------------------------------------

        should_alert = (
            should_alert_cluster(
                cluster,
                previous
            )
        )

        if should_alert:

            alert_clusters.append(
                cluster
            )

            if previous is None:

                print(
                    f"🆕 New alert cluster: "
                    f"{cid}"
                )

            else:

                old_score = float(
                    previous.get(
                        "risk",
                        0
                    )
                )

                print(
                    f"🚨 Cluster escalation: "
                    f"{cid} "
                    f"{old_score}/100 → "
                    f"{risk['score']}/100"
                )

    # ========================================================
    # ALERT SUMMARY
    # ========================================================

    print(
        f"🚨 Alert clusters: "
        f"{len(alert_clusters)}"
    )

    # ========================================================
    # REPORT
    # ========================================================

    if alert_clusters:

        send_fire_report(

            alert_clusters,

            raw_count,

            len(events),

            stats[
                "outside_saudi"
            ]

        )

    else:

        send_no_fire_report(

            raw_count,

            len(events),

            stats[
                "outside_saudi"
            ]

        )

    # ========================================================
    # SAVE STATE
    # ========================================================

    state[
        "seen"
    ] = seen

    state[
        "clusters"
    ] = current_cluster_state

    save_state(
        state
    )

    # ========================================================
    # FINAL
    # ========================================================

    print(
        "=" * 70
    )

    print(
        "🇸🇦 Saudi boundary validation completed"
    )

    print(
        "🧠 Advanced verification completed"
    )

    print(
        "📈 Persistence analysis completed"
    )

    print(
        "🚨 Escalation analysis completed"
    )

    print(
        "🤖 V5.6 Advanced Geographic & Verification Engine"
    )

    print(
        "✅ V5.6 completed successfully"
    )

    print(
        "=" * 70
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
