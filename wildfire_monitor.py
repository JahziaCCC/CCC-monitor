import os
import json
import math
import datetime
import time
import requests


# ============================================================
# 🔥 Saudi Wildfire Intelligence V5.9.4
# Government Monitoring Center Engine
#
# NASA FIRMS + VIIRS
#
# V5.9.4:
# - Stable Event Identity
# - Historical Event Matching
# - Event Lifecycle
# - Risk Engine
# - Verification Engine
# - Persistence Engine
# - Trend Intelligence
# - Operational Priority
# - Trigger Intelligence
# - National Situation Index
# - Detection vs Operational Events
# - Alert Cooldown
# - Arabic Telegram Executive Reporting
#
# PRESERVED:
# - Saudi Polygon Validation
# - BBOX
# - Natural Fire Filtering
# - FRP Filtering
# - Duplicate Protection
# - Spatial Clustering
# - Temporal Persistence
# - Historical Memory
# ============================================================


# ============================================================
# ENVIRONMENT
# ============================================================

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
FIRMS_KEY = os.environ["FIRMS_API_KEY"]


# ============================================================
# TIMEZONE
# ============================================================

KSA_TZ = datetime.timezone(
    datetime.timedelta(hours=3)
)


# ============================================================
# STATE
# ============================================================

STATE_FILE = "wildfire_state_v594.json"


# ============================================================
# 🇸🇦 SAUDI ARABIA BBOX
# ============================================================

BBOX = (
    34.5,
    16.0,
    55.8,
    32.6
)


# ============================================================
# 🛰️ FIRMS SOURCES
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

CLUSTER_MEMORY_HOURS = 72
HISTORY_MEMORY_HOURS = 168

ALERT_NEW_CLUSTER = True
ALERT_COOLDOWN_HOURS = 6

NEW_CLUSTER_MIN_RISK = 50
NEW_CLUSTER_MIN_COUNT = 2
NEW_CLUSTER_STRONG_FRP = 40

MAX_HISTORY_CLUSTERS = 500


# ============================================================
# TEMPORAL SETTINGS
# ============================================================

TEMPORAL_MATCH_RADIUS_KM = 5.0
PERSISTENCE_WINDOW_HOURS = 72

PERSISTENCE_TIME_WEIGHT = 0.55
PERSISTENCE_COUNT_WEIGHT = 0.45


# ============================================================
# 🏛️ GOVERNMENT MONITORING CENTER
# ============================================================

OPERATIONAL_EVENT_MIN_PRIORITY = 35

MONITORING_PRIORITY = 35
VERIFICATION_PRIORITY = 60
ESCALATION_PRIORITY = 75
CRITICAL_PRIORITY = 90


# ============================================================
# HTTP
# ============================================================

HTTP_HEADERS = {
    "User-Agent": "Saudi-Wildfire-Intelligence-V5.9.4",
    "Accept": "text/csv,*/*",
    "Connection": "close",
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
        "history": {},
        "alerts": {},
        "events": {},
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

        for key in [
            "seen",
            "clusters",
            "history",
            "alerts",
            "events"
        ]:

            state.setdefault(
                key,
                {}
            )

        state.setdefault(
            "last_run",
            None
        )

        return state

    except Exception as e:

        print(
            f"⚠️ State load error: {e}"
        )

        return default_state()


# ============================================================
# SAVE STATE
# ============================================================

def save_state(state):

    now = now_utc()

    seen_cutoff = (
        now -
        datetime.timedelta(
            hours=CLUSTER_MEMORY_HOURS
        )
    )

    history_cutoff = (
        now -
        datetime.timedelta(
            hours=HISTORY_MEMORY_HOURS
        )
    )

    # --------------------------------------------------------
    # SEEN
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

            if dt >= seen_cutoff:
                cleaned_seen[key] = value

        except Exception:
            continue

    state["seen"] = cleaned_seen

    # --------------------------------------------------------
    # CLUSTERS
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

            if dt >= seen_cutoff:
                cleaned_clusters[key] = value

        except Exception:
            continue

    state["clusters"] = cleaned_clusters

    # --------------------------------------------------------
    # HISTORY
    # --------------------------------------------------------

    cleaned_history = {}

    for key, value in state.get(
        "history",
        {}
    ).items():

        try:

            dt = datetime.datetime.fromisoformat(
                value.get(
                    "last_seen"
                )
            )

            if dt >= history_cutoff:
                cleaned_history[key] = value

        except Exception:
            continue

    if len(cleaned_history) > MAX_HISTORY_CLUSTERS:

        ordered = sorted(
            cleaned_history.items(),
            key=lambda item:
            item[1].get(
                "last_seen",
                ""
            ),
            reverse=True
        )

        cleaned_history = dict(
            ordered[
                :MAX_HISTORY_CLUSTERS
            ]
        )

    state["history"] = cleaned_history

    # --------------------------------------------------------
    # ALERTS
    # --------------------------------------------------------

    cleaned_alerts = {}

    for key, value in state.get(
        "alerts",
        {}
    ).items():

        try:

            dt = datetime.datetime.fromisoformat(
                value
            )

            if dt >= history_cutoff:
                cleaned_alerts[key] = value

        except Exception:
            continue

    state["alerts"] = cleaned_alerts

    # --------------------------------------------------------
    # EVENTS
    # --------------------------------------------------------

    cleaned_events = {}

    for key, value in state.get(
        "events",
        {}
    ).items():

        try:

            dt = datetime.datetime.fromisoformat(
                value.get(
                    "last_seen"
                )
            )

            if dt >= history_cutoff:
                cleaned_events[key] = value

        except Exception:
            continue

    state["events"] = cleaned_events

    state["last_run"] = (
        now.isoformat()
    )

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
        "https://api.telegram.org/"
        f"bot{BOT}/sendMessage"
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
        "📨 Telegram report sent"
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
            for i in range(
                len(header)
            )
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
                f"HTTP "
                f"{response.status_code}"
            )

        except Exception as e:

            last_error = str(e)

        time.sleep(3)

    print(
        f"❌ FIRMS API error "
        f"({source}): "
        f"{last_error}"
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

        intersects = (
            (yi > y)
            !=
            (yj > y)
        ) and (
            x <
            (xj - xi)
            *
            (y - yi)
            /
            (yj - yi)
            +
            xi
        )

        if intersects:
            inside = not inside

        j = i

    return inside


# ============================================================
# SAUDI VALIDATION
# ============================================================

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

        number = float(
            value
        )

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

    lat1_rad = math.radians(
        lat1
    )

    lat2_rad = math.radians(
        lat2
    )

    dlat = (
        lat2_rad -
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
        math.cos(
            lat1_rad
        )
        *
        math.cos(
            lat2_rad
        )
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

        min_lon, min_lat, max_lon, max_lat = BBOX

        if not (
            min_lat <= lat <= max_lat
            and
            min_lon <= lon <= max_lon
        ):

            outside_bbox += 1
            continue

        if not is_inside_saudi(
            lat,
            lon
        ):

            outside_saudi += 1
            continue

        if not is_natural_fire(
            row
        ):

            non_natural += 1
            continue

        acquisition = (
            parse_acquisition_datetime(
                row.get(
                    "acq_date"
                ),
                row.get(
                    "acq_time"
                )
            )
        )

        if acquisition is None:
            continue

        age_hours = (
            current_time -
            acquisition
        ).total_seconds() / 3600

        if age_hours < 0:
            age_hours = 0

        if age_hours > MAX_AGE_HOURS:

            old_events += 1
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

            low_frp += 1
            continue

        confidence = confidence_score(
            row.get(
                "confidence"
            )
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

        "outside_bbox": outside_bbox,

        "outside_saudi": outside_saudi,

        "invalid_coordinates":
            invalid_coordinates,

        "old_events":
            old_events,

        "low_frp":
            low_frp,

        "non_natural":
            non_natural

    }

    return (
        events,
        stats
    )


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
                distance
                <=
                CLUSTER_RADIUS_KM
                and
                time_difference
                <=
                CLUSTER_TIME_MINUTES
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
                    cluster[
                        "max_frp"
                    ],
                    event["frp"]
                )

                cluster[
                    "latest"
                ] = max(
                    cluster[
                        "latest"
                    ],
                    event["datetime"]
                )

                count = len(
                    cluster[
                        "events"
                    ]
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

                "events": [
                    event
                ],

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

def frp_score_value(
    max_frp
):

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

def cluster_score_value(
    count
):

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
# PERSISTENCE
# ============================================================

def calculate_persistence(
    cluster,
    previous
):

    if not previous:
        return 20

    previous_count = int(
        previous.get(
            "observations",
            1
        )
    )

    previous_last_seen_raw = (
        previous.get(
            "last_seen"
        )
    )

    if not previous_last_seen_raw:
        return 20

    try:

        previous_last_seen = (
            datetime.datetime.fromisoformat(
                previous_last_seen_raw
            )
        )

    except Exception:

        return 20

    elapsed_hours = (
        now_utc()
        -
        previous_last_seen
    ).total_seconds() / 3600

    if elapsed_hours < 0:
        elapsed_hours = 0

    if (
        elapsed_hours
        >
        PERSISTENCE_WINDOW_HOURS
    ):
        return 20

    recency = max(
        0,
        100 -
        (
            elapsed_hours
            /
            PERSISTENCE_WINDOW_HOURS
            *
            100
        )
    )

    if previous_count >= 10:
        observation_score = 100

    elif previous_count >= 7:
        observation_score = 90

    elif previous_count >= 5:
        observation_score = 80

    elif previous_count >= 3:
        observation_score = 65

    elif previous_count >= 2:
        observation_score = 50

    else:
        observation_score = 25

    persistence = (
        recency
        *
        PERSISTENCE_TIME_WEIGHT
        +
        observation_score
        *
        PERSISTENCE_COUNT_WEIGHT
    )

    return round(
        max(
            20,
            min(
                100,
                persistence
            )
        )
    )


# ============================================================
# RISK
# ============================================================

def calculate_risk(
    cluster,
    persistence_score=20
):

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
            for e in
            cluster["events"]
        )
        /
        count
    )

    frp_score = frp_score_value(
        max_frp
    )

    cluster_score = cluster_score_value(
        count
    )

    risk = (
        frp_score * 0.35
        +
        cluster_score * 0.25
        +
        avg_confidence * 0.20
        +
        persistence_score * 0.20
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

        "confidence":
            round(
                avg_confidence
            ),

        "max_frp": max_frp,

        "total_frp": total_frp,

        "count": count

    }


# ============================================================
# VERIFICATION
# ============================================================

def calculate_verification_score(
    cluster,
    persistence_score
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
            for e in
            cluster["events"]
        )
        /
        count
    )

    cluster_component = (
        cluster_score_value(
            count
        )
    )

    frp_component = (
        frp_score_value(
            max_frp
        )
    )

    verification = (
        cluster_component * 0.35
        +
        frp_component * 0.30
        +
        avg_confidence * 0.20
        +
        persistence_score * 0.15
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
    verification,
    persistence
):

    score = risk["score"]
    count = risk["count"]
    max_frp = risk["max_frp"]

    if (
        score >= 80
        and
        verification >= 75
    ):

        return (
            "حريق محتمل عالي الأولوية",
            "بؤرة حرارية قوية ومتجمعة وتستدعي التحقق العاجل"
        )

    if (
        score >= 65
        and
        count >= 3
        and
        persistence >= 50
    ):

        return (
            "حريق محتمل مرتفع الأولوية",
            "نشاط حراري متجمع ومستمر ويستحق المتابعة المكثفة"
        )

    if (
        score >= 60
        and
        count >= 3
    ):

        return (
            "بؤرة حرارية مرتفعة الأولوية",
            "تجمع حراري قوي متعدد النقاط ويستحق المتابعة"
        )

    if (
        max_frp >= NEW_CLUSTER_STRONG_FRP
        and
        count == 1
    ):

        return (
            "نقطة حرارية قوية",
            "شدة حرارية مرتفعة وتحتاج إلى تحقق إضافي"
        )

    if score >= 50:

        return (
            "بؤرة حرارية تحتاج مراقبة",
            "بؤرة حرارية ملحوظة وتحتاج إلى المتابعة"
        )

    return (
        "نشاط حراري منخفض الأولوية",
        "نشاط حراري محدود ولا يستدعي تنبيهًا عاجلًا"
    )


# ============================================================
# STABLE SPATIAL ID
# ============================================================

def spatial_key(
    lat,
    lon
):

    return (
        f"{round(lat, 1):.1f}_"
        f"{round(lon, 1):.1f}"
    )


# ============================================================
# CLUSTER ID
# ============================================================

def cluster_id(
    cluster
):

    return spatial_key(
        cluster["center"]["lat"],
        cluster["center"]["lon"]
    )


# ============================================================
# HISTORICAL MATCH
# ============================================================

def find_previous_cluster(
    cluster,
    previous_clusters
):

    current_lat = (
        cluster["center"]["lat"]
    )

    current_lon = (
        cluster["center"]["lon"]
    )

    current_time = now_utc()

    best_match = None
    best_distance = None

    for previous in (
        previous_clusters.values()
    ):

        try:

            previous_last_seen = (
                datetime.datetime.fromisoformat(
                    previous.get(
                        "last_seen"
                    )
                )
            )

        except Exception:

            continue

        age_hours = (
            current_time
            -
            previous_last_seen
        ).total_seconds() / 3600

        if age_hours < 0:
            age_hours = 0

        if (
            age_hours
            >
            CLUSTER_MEMORY_HOURS
        ):
            continue

        try:

            previous_lat = float(
                previous.get(
                    "lat"
                )
            )

            previous_lon = float(
                previous.get(
                    "lon"
                )
            )

        except Exception:

            continue

        distance = distance_km(
            current_lat,
            current_lon,
            previous_lat,
            previous_lon
        )

        if (
            distance
            >
            TEMPORAL_MATCH_RADIUS_KM
        ):
            continue

        if (
            best_distance is None
            or
            distance
            <
            best_distance
        ):

            best_distance = distance
            best_match = previous

    return best_match


# ============================================================
# FIND EXISTING EVENT
# ============================================================

def find_existing_event(
    cluster,
    state
):

    events = state.get(
        "events",
        {}
    )

    center = cluster[
        "center"
    ]

    current_lat = center[
        "lat"
    ]

    current_lon = center[
        "lon"
    ]

    best_event = None
    best_distance = None

    for event_id, event in (
        events.items()
    ):

        try:

            last_seen = (
                datetime.datetime.fromisoformat(
                    event.get(
                        "last_seen"
                    )
                )
            )

        except Exception:

            continue

        age_hours = (
            now_utc()
            -
            last_seen
        ).total_seconds() / 3600

        if (
            age_hours
            >
            HISTORY_MEMORY_HOURS
        ):
            continue

        try:

            lat = float(
                event.get(
                    "lat"
                )
            )

            lon = float(
                event.get(
                    "lon"
                )
            )

        except Exception:

            continue

        distance = distance_km(
            current_lat,
            current_lon,
            lat,
            lon
        )

        if (
            distance
            >
            TEMPORAL_MATCH_RADIUS_KM
        ):
            continue

        if (
            best_distance is None
            or
            distance
            <
            best_distance
        ):

            best_distance = distance
            best_event = (
                event_id,
                event
            )

    return best_event


# ============================================================
# EVENT ID
# ============================================================

def generate_event_id(
    cluster,
    state
):

    existing = state.get(
        "events",
        {}
    )

    existing_match = (
        find_existing_event(
            cluster,
            state
        )
    )

    if existing_match:

        return existing_match[0]

    center = cluster[
        "center"
    ]

    lat = abs(
        round(
            center["lat"]
            * 10
        )
    )

    lon = abs(
        round(
            center["lon"]
            * 10
        )
    )

    date_part = (
        datetime.datetime
        .now(KSA_TZ)
        .strftime(
            "%Y%m%d"
        )
    )

    base = (
        f"KSA-WF-"
        f"{date_part}-"
        f"{lat:04d}-"
        f"{lon:04d}"
    )

    event_id = base
    counter = 1

    while (
        event_id in existing
    ):

        counter += 1

        event_id = (
            f"{base}-"
            f"{counter:02d}"
        )

    return event_id


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

    new_score = (
        cluster[
            "risk"
        ]["score"]
    )

    difference = (
        new_score
        -
        old_score
    )

    if (
        difference
        >=
        RISK_CHANGE_ALERT
    ):

        return (
            "📈 تصاعد",
            f"ارتفاع مستوى الخطورة بمقدار {difference} نقطة"
        )

    if (
        difference
        <=
        -RISK_CHANGE_ALERT
    ):

        return (
            "📉 تراجع",
            f"انخفاض مستوى الخطورة بمقدار {abs(difference)} نقطة"
        )

    return (
        "➡️ مستقر",
        "مستوى الخطورة مستقر نسبيًا"
    )


# ============================================================
# TRIGGER INTELLIGENCE
# ============================================================

def calculate_triggers(
    cluster,
    previous,
    risk,
    verification,
    persistence,
    trend
):

    triggers = []

    count = risk[
        "count"
    ]

    max_frp = risk[
        "max_frp"
    ]

    if previous is None:

        triggers.append(
            "🆕 حدث جديد"
        )

    if count >= 3:

        triggers.append(
            "🔥 تعدد النقاط"
        )

    if count >= 5:

        triggers.append(
            "🧩 تجمع حراري قوي"
        )

    if max_frp >= 40:

        triggers.append(
            "⚡ شدة حرارية مرتفعة"
        )

    if max_frp >= 70:

        triggers.append(
            "⚡⚡ شدة حرارية شديدة"
        )

    if persistence >= 50:

        triggers.append(
            "⏱️ استمرارية حرارية"
        )

    if verification >= 70:

        triggers.append(
            "🧠 تحقق مرتفع"
        )

    if "تصاعد" in trend:

        triggers.append(
            "📈 تصاعد الخطورة"
        )

    if not triggers:

        triggers.append(
            "👁️ رصد حراري محدود"
        )

    return triggers


# ============================================================
# OPERATIONAL PRIORITY
# ============================================================

def calculate_operational_priority(
    risk,
    verification,
    persistence,
    trend,
    previous
):

    score = (
        risk["score"]
        * 0.45
        +
        verification
        * 0.25
        +
        persistence
        * 0.15
    )

    if "تصاعد" in trend:

        score += 8

    if (
        previous is None
        and
        risk["score"] >= 50
    ):

        score += 4

    if risk[
        "max_frp"
    ] >= 70:

        score += 8

    score = round(
        min(
            100,
            max(
                0,
                score
            )
        )
    )

    if score >= CRITICAL_PRIORITY:

        level = "حرج"
        emoji = "🔴"
        decision = "تصعيد عاجل"

    elif score >= ESCALATION_PRIORITY:

        level = "عال"
        emoji = "🟠"
        decision = "تصعيد"

    elif score >= VERIFICATION_PRIORITY:

        level = "متوسط"
        emoji = "🟡"
        decision = "تحقق"

    elif score >= MONITORING_PRIORITY:

        level = "متوسط"
        emoji = "🟡"
        decision = "مراقبة"

    else:

        level = "منخفض"
        emoji = "🟢"
        decision = "روتينية"

    return {

        "score": score,

        "level": level,

        "emoji": emoji,

        "decision": decision

    }


# ============================================================
# EVENT LIFECYCLE
# ============================================================

def determine_lifecycle(
    operational,
    previous_event,
    previous
):

    decision = (
        operational[
            "decision"
        ]
    )

    if decision == "تصعيد عاجل":

        return (
            "🔴 "
            "ESCALATED_CRITICAL"
        )

    if decision == "تصعيد":

        return (
            "🟠 "
            "ESCALATED"
        )

    if decision == "تحقق":

        return (
            "🟡 "
            "VERIFICATION"
        )

    if decision == "مراقبة":

        if previous_event:

            return (
                "👁️ "
                "MONITORING"
            )

        return (
            "🆕 NEW → "
            "MONITORING"
        )

    if previous_event:

        return (
            "🟢 STABLE"
        )

    return "🆕 NEW"


# ============================================================
# OPERATIONAL DECISION
# ============================================================

def operational_decision(
    operational,
    trend,
    persistence
):

    decision = (
        operational[
            "decision"
        ]
    )

    if decision == "تصعيد عاجل":

        return (
            "🚨 تصعيد عاجل",
            "رفع الحالة فورًا للتحقق والتعامل التشغيلي."
        )

    if decision == "تصعيد":

        return (
            "🚨 تصعيد",
            "رفع مستوى المتابعة والتحقق من الحدث."
        )

    if decision == "تحقق":

        return (
            "🟡 تحقق",
            "الحدث يستحق التحقق عبر مصدر إضافي أو ميداني."
        )

    if decision == "مراقبة":

        if "تصاعد" in trend:

            return (
                "👁️ مراقبة مشددة",
                "مراقبة الحدث بسبب مؤشرات التصاعد."
            )

        if persistence >= 50:

            return (
                "👁️ مراقبة مشددة",
                "مراقبة الحدث بسبب الاستمرارية."
            )

        return (
            "👁️ مراقبة",
            "مراقبة الحدث دون تصعيد فوري."
        )

    return (
        "🟢 روتينية",
        "لا توجد حاجة لتصعيد تشغيلي حاليًا."
    )


# ============================================================
# NATIONAL SITUATION
# ============================================================

def calculate_national_situation(
    clusters
):

    if not clusters:

        return {

            "score": 0,

            "level": "طبيعي",

            "emoji": "🟢",

            "description":
                "لا توجد مؤشرات تشغيلية مهمة."

        }

    priorities = [
        c[
            "operational"
        ]["score"]
        for c in clusters
    ]

    highest = max(
        priorities
    )

    medium_high = sum(
        1
        for p in priorities
        if p >= VERIFICATION_PRIORITY
    )

    escalations = sum(
        1
        for p in priorities
        if p >= ESCALATION_PRIORITY
    )

    average = (
        sum(priorities)
        /
        len(priorities)
    )

    score = (
        highest * 0.55
        +
        average * 0.25
        +
        min(
            100,
            medium_high * 10
        )
        * 0.10
        +
        min(
            100,
            escalations * 25
        )
        * 0.10
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

        description = (
            "الموقف الوطني يستدعي تصعيدًا تشغيليًا."
        )

    elif score >= 60:

        level = "مرتفع"
        emoji = "🟠"

        description = (
            "توجد مؤشرات تستدعي رفع مستوى المراقبة."
        )

    elif score >= 40:

        level = "تحت المراقبة"
        emoji = "🟡"

        description = (
            "توجد أحداث حرارية تحت المراقبة."
        )

    else:

        level = "طبيعي"
        emoji = "🟢"

        description = (
            "الموقف الوطني ضمن المستويات الاعتيادية."
        )

    return {

        "score": score,

        "level": level,

        "emoji": emoji,

        "description":
            description

    }


# ============================================================
# REGION
# ============================================================

def approximate_region(
    lat,
    lon
):

    if lat >= 29:

        return (
            "الحدود الشمالية / الجوف / تبوك"
        )

    if lat >= 27:

        if lon < 42:

            return (
                "تبوك / شمال غرب المملكة"
            )

        return (
            "حائل / الحدود الشمالية"
        )

    if lat >= 24:

        if lon < 42:

            return (
                "المدينة المنورة / شمال غرب المملكة"
            )

        if lon < 48:

            return (
                "القصيم / الرياض"
            )

        return (
            "المنطقة الشرقية"
        )

    if lat >= 22:

        if lon < 42:

            return (
                "مكة المكرمة / المدينة المنورة"
            )

        if lon < 48:

            return (
                "الرياض / وسط المملكة"
            )

        return (
            "المنطقة الشرقية"
        )

    if lat >= 18:

        if lon < 44:

            return (
                "عسير / جازان"
            )

        if lon < 48:

            return (
                "نجران"
            )

        return (
            "المنطقة الشرقية"
        )

    return (
        "جازان / جنوب المملكة"
    )


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
# ALERT COOLDOWN
# ============================================================

def alert_allowed(
    cid,
    state
):

    alerts = state.get(
        "alerts",
        {}
    )

    last_alert_raw = (
        alerts.get(cid)
    )

    if not last_alert_raw:
        return True

    try:

        last_alert = (
            datetime.datetime.fromisoformat(
                last_alert_raw
            )
        )

    except Exception:

        return True

    elapsed = (
        now_utc()
        -
        last_alert
    ).total_seconds() / 3600

    if (
        elapsed
        >=
        ALERT_COOLDOWN_HOURS
    ):

        return True

    print(
        f"⏸️ Alert cooldown active: "
        f"{cid} | "
        f"{elapsed:.1f}h"
    )

    return False


def mark_alert(
    cid,
    state
):

    state.setdefault(
        "alerts",
        {}
    )

    state[
        "alerts"
    ][cid] = (
        now_utc().isoformat()
    )


# ============================================================
# NEW CLUSTER DECISION
# ============================================================

def is_significant_new_cluster(
    cluster
):

    risk = cluster[
        "risk"
    ]

    if (
        risk["score"]
        >=
        NEW_CLUSTER_MIN_RISK
    ):

        return True

    if (
        risk["count"]
        >=
        NEW_CLUSTER_MIN_COUNT
        and
        risk["max_frp"]
        >=
        20
    ):

        return True

    if (
        risk["count"]
        ==
        1
        and
        risk["max_frp"]
        >=
        NEW_CLUSTER_STRONG_FRP
    ):

        return True

    return False


# ============================================================
# EVENT MEMORY
# ============================================================

def update_event_record(
    state,
    event_id,
    cluster,
    lifecycle,
    operational,
    triggers,
    first_seen
):

    events = state.setdefault(
        "events",
        {}
    )

    old = events.get(
        event_id,
        {}
    )

    observations = int(
        old.get(
            "observations",
            0
        )
    ) + 1

    previous_risk = old.get(
        "risk",
        cluster[
            "risk"
        ]["score"]
    )

    risk_change = (
        cluster[
            "risk"
        ]["score"]
        -
        float(
            previous_risk
        )
    )

    events[event_id] = {

        "event_id":
            event_id,

        "lat":
            cluster[
                "center"
            ]["lat"],

        "lon":
            cluster[
                "center"
            ]["lon"],

        "first_seen":
            old.get(
                "first_seen",
                first_seen
            ),

        "last_seen":
            now_utc().isoformat(),

        "observations":
            observations,

        "risk":
            cluster[
                "risk"
            ]["score"],

        "previous_risk":
            previous_risk,

        "risk_change":
            risk_change,

        "verification":
            cluster[
                "verification"
            ],

        "persistence":
            cluster[
                "persistence"
            ],

        "operational_priority":
            operational[
                "score"
            ],

        "operational_level":
            operational[
                "level"
            ],

        "decision":
            operational[
                "decision"
            ],

        "lifecycle":
            lifecycle,

        "triggers":
            triggers

    }


# ============================================================
# REPORT
# ============================================================

def send_monitoring_report(
    clusters,
    raw_count,
    normalized_count,
    outside_saudi,
    national
):

    clusters = sorted(
        clusters,
        key=lambda c: (
            c[
                "operational"
            ]["score"],

            c[
                "risk"
            ]["score"],

            c[
                "verification"
            ],

            c[
                "persistence"
            ],

            c[
                "risk"
            ]["max_frp"]
        ),
        reverse=True
    )

    operational_events = [
        c for c in clusters
        if c[
            "operational"
        ]["score"]
        >=
        OPERATIONAL_EVENT_MIN_PRIORITY
    ]

    verification_events = [
        c for c in clusters
        if c[
            "operational"
        ]["score"]
        >=
        VERIFICATION_PRIORITY
    ]

    escalations = [
        c for c in clusters
        if c[
            "operational"
        ]["score"]
        >=
        ESCALATION_PRIORITY
    ]

    critical = [
        c for c in clusters
        if c[
            "operational"
        ]["score"]
        >=
        CRITICAL_PRIORITY
    ]

    high = [
        c for c in clusters
        if (
            c[
                "operational"
            ]["score"]
            >=
            ESCALATION_PRIORITY
            and
            c[
                "operational"
            ]["score"]
            <
            CRITICAL_PRIORITY
        )
    ]

    medium = [
        c for c in operational_events
        if (
            c[
                "operational"
            ]["score"]
            >=
            MONITORING_PRIORITY
            and
            c[
                "operational"
            ]["score"]
            <
            ESCALATION_PRIORITY
        )
    ]

    low = [
        c for c in clusters
        if c[
            "operational"
        ]["score"]
        <
        MONITORING_PRIORITY
    ]

    new_events = [
        c for c in clusters
        if "جديدة"
        in c.get(
            "trend",
            ""
        )
    ]

    rising = [
        c for c in clusters
        if "تصاعد"
        in c.get(
            "trend",
            ""
        )
    ]

    declining = [
        c for c in clusters
        if "تراجع"
        in c.get(
            "trend",
            ""
        )
    ]

    message = []

    message.append(
        "🔥 مركز مراقبة حرائق السعودية — V5.9.4"
    )

    message.append(
        f"🕒 {now_ksa()}"
    )

    message.append("")

    message.append(
        "🏛️ الحالة التشغيلية:"
    )

    message.append(
        f"{national['emoji']} "
        f"{national['level']}"
    )

    message.append(
        f"🎯 مؤشر المركز: "
        f"{national['score']}/100"
    )

    message.append(
        national[
            "description"
        ]
    )

    message.append("")

    message.append(
        "📡 الموقف الوطني:"
    )

    message.append(
        f"🔥 البؤر الحرارية: "
        f"{len(clusters)}"
    )

    message.append(
        f"👁️ أحداث تحت المراقبة: "
        f"{len(operational_events)}"
    )

    message.append(
        f"🟡 أحداث تحتاج تحقق: "
        f"{len(verification_events)}"
    )

    message.append(
        f"🚨 حالات تصعيد: "
        f"{len(escalations)}"
    )

    message.append(
        f"🔴 حرجة: {len(critical)} | "
        f"🟠 عالية: {len(high)} | "
        f"🟡 متوسطة: {len(medium)} | "
        f"🟢 منخفضة: {len(low)}"
    )

    message.append(
        f"🆕 جديدة: {len(new_events)} | "
        f"📈 متصاعدة: {len(rising)} | "
        f"📉 متراجعة: {len(declining)}"
    )

    message.append("")

    if operational_events:

        highest = (
            operational_events[0]
        )

        op = highest[
            "operational"
        ]

        risk = highest[
            "risk"
        ]

        message.append(
            "🎯 أعلى أولوية تشغيلية:"
        )

        message.append(
            f"{op['emoji']} "
            f"{op['level']} — "
            f"{op['score']}/100"
        )

        message.append(
            highest[
                "decision"
            ]
        )

        message.append(
            highest[
                "decision_description"
            ]
        )

        message.append("")

        message.append(
            "🚨 أعلى مستوى خطورة:"
        )

        message.append(
            f"{risk['emoji']} "
            f"{risk['level']} — "
            f"{risk['score']}/100"
        )

        message.append("")

        message.append(
            "🧠 درجة التحقق الذكي:"
        )

        message.append(
            f"{highest['verification']}/100"
        )

        message.append("")

        message.append(
            "⏱️ الاستمرارية:"
        )

        message.append(
            f"{highest['persistence']}/100"
        )

    else:

        message.append(
            "🎯 أعلى أولوية تشغيلية:"
        )

        message.append(
            "🟢 روتينية — لا توجد حالات تشغيلية."
        )

    message.append("")

    message.append(
        "📌 أبرز الأحداث:"
    )

    top = clusters[
        :TOP_CLUSTERS
    ]

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

        operational = cluster[
            "operational"
        ]

        region = approximate_region(
            center["lat"],
            center["lon"]
        )

        message.append("")

        message.append(
            f"{index}) "
            f"{operational['emoji']} "
            f"أولوية {operational['level']} — "
            f"{operational['score']}/100"
        )

        message.append(
            f"🆔 الحدث: "
            f"{cluster['event_id']}"
        )

        message.append(
            f"🚨 الخطورة: "
            f"{risk['emoji']} "
            f"{risk['level']} — "
            f"{risk['score']}/100"
        )

        message.append(
            f"📍 الموقع: "
            f"{center['lat']:.4f}, "
            f"{center['lon']:.4f}"
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
            f"🎯 التحقق: "
            f"{confidence_ar(risk['confidence'])}"
        )

        message.append(
            f"🤖 التصنيف: "
            f"{cluster['classification']}"
        )

        message.append(
            f"📈 الاتجاه: "
            f"{cluster['trend']}"
        )

        message.append(
            f"🔄 الحالة: "
            f"{cluster['lifecycle']}"
        )

        message.append(
            f"🧠 درجة التحقق: "
            f"{cluster['verification']}/100"
        )

        message.append(
            f"⏱️ الاستمرارية: "
            f"{cluster['persistence']}/100"
        )

        message.append(
            f"📊 الرصد المتكرر: "
            f"{cluster['observations']}"
        )

        message.append(
            "🧠 مؤشرات القرار:"
        )

        for trigger in cluster[
            "triggers"
        ][:5]:

            message.append(
                f"   • {trigger}"
            )

        message.append(
            f"🏛️ القرار: "
            f"{cluster['decision']}"
        )

        message.append(
            f"📝 الإجراء: "
            f"{cluster['decision_description']}"
        )

        message.append(
            f"📍 الخريطة: "
            f"{google_maps(center['lat'], center['lon'])}"
        )

    message.append("")

    message.append(
        "📊 بيانات الرصد:"
    )

    message.append(
        f"FIRMS: {raw_count}"
    )

    message.append(
        f"بعد التحليل: "
        f"{normalized_count}"
    )

    message.append(
        f"خارج حدود المملكة: "
        f"{outside_saudi}"
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
        "Saudi Wildfire Intelligence V5.9.4"
    )

    message.append("")

    message.append(
        "🏛️ طبقة مركز المراقبة:"
    )

    message.append(
        "Government Monitoring Center Engine"
    )

    message.append("")

    message.append(
        "🧠 الذكاء التشغيلي:"
    )

    message.append(
        "Risk + Verification + Persistence + "
        "Trend + Operational Priority + "
        "Lifecycle + Trigger Intelligence"
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
        "\n".join(message)
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)

    print(
        "🔥 Saudi Wildfire Intelligence V5.9.4"
    )

    print(
        f"🕒 {now_ksa()}"
    )

    print(
        "🏛️ Government Monitoring Center ENABLED"
    )

    print(
        "🇸🇦 Geographic Boundary Validation ENABLED"
    )

    print(
        "⏱️ Temporal Persistence Engine ENABLED"
    )

    print(
        "🧠 Historical Memory ENABLED"
    )

    print(
        "🎯 Operational Priority ENABLED"
    )

    print(
        "🔄 Event Lifecycle ENABLED"
    )

    print(
        "🧠 Trigger Intelligence ENABLED"
    )

    print("=" * 70)

    state = load_state()

    seen = state.get(
        "seen",
        {}
    )

    previous_clusters = {}

    previous_clusters.update(
        state.get(
            "history",
            {}
        )
    )

    previous_clusters.update(
        state.get(
            "clusters",
            {}
        )
    )

    all_rows = []

    # ========================================================
    # FIRMS COLLECTION
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
        f"🌿 Non-natural events removed: "
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

        seen[
            uid
        ] = now_utc().isoformat()

        new_events.append(
            event
        )

    print(
        f"🆕 New detections: "
        f"{len(new_events)}"
    )

    # ========================================================
    # CLUSTER
    # ========================================================

    clusters = cluster_events(
        events
    )

    print(
        f"🔥 Current clusters: "
        f"{len(clusters)}"
    )

    # ========================================================
    # PROCESS CLUSTERS
    # ========================================================

    processed_clusters = []

    current_cluster_state = {}

    for cluster in clusters:

        previous = find_previous_cluster(
            cluster,
            previous_clusters
        )

        persistence = (
            calculate_persistence(
                cluster,
                previous
            )
        )

        cluster[
            "persistence"
        ] = persistence

        risk = calculate_risk(
            cluster,
            persistence
        )

        cluster[
            "risk"
        ] = risk

        verification = (
            calculate_verification_score(
                cluster,
                persistence
            )
        )

        cluster[
            "verification"
        ] = verification

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

        classification, explanation = (
            classify_cluster(
                risk,
                verification,
                persistence
            )
        )

        cluster[
            "classification"
        ] = classification

        cluster[
            "explanation"
        ] = explanation

        operational = (
            calculate_operational_priority(
                risk,
                verification,
                persistence,
                trend,
                previous
            )
        )

        cluster[
            "operational"
        ] = operational

        triggers = calculate_triggers(
            cluster,
            previous,
            risk,
            verification,
            persistence,
            trend
        )

        cluster[
            "triggers"
        ] = triggers

        decision, decision_description = (
            operational_decision(
                operational,
                trend,
                persistence
            )
        )

        cluster[
            "decision"
        ] = decision

        cluster[
            "decision_description"
        ] = decision_description

        # ----------------------------------------------------
        # STABLE EVENT ID
        # ----------------------------------------------------

        existing_event = (
            find_existing_event(
                cluster,
                state
            )
        )

        if existing_event:

            event_id = existing_event[0]

        else:

            event_id = generate_event_id(
                cluster,
                state
            )

        cluster[
            "event_id"
        ] = event_id

        # ----------------------------------------------------
        # EVENT OBSERVATIONS
        # ----------------------------------------------------

        old_event = state.get(
            "events",
            {}
        ).get(
            event_id
        )

        if old_event:

            observations = int(
                old_event.get(
                    "observations",
                    0
                )
            ) + 1

            first_seen = old_event.get(
                "first_seen",
                now_utc().isoformat()
            )

        else:

            observations = 1

            first_seen = (
                now_utc().isoformat()
            )

        cluster[
            "observations"
        ] = observations

        # ----------------------------------------------------
        # LIFECYCLE
        # ----------------------------------------------------

        lifecycle = (
            determine_lifecycle(
                operational,
                old_event,
                previous
            )
        )

        cluster[
            "lifecycle"
        ] = lifecycle

        # ----------------------------------------------------
        # CURRENT CLUSTER STATE
        # ----------------------------------------------------

        cid = cluster_id(
            cluster
        )

        current_cluster_state[
            cid
        ] = {

            "event_id":
                event_id,

            "risk":
                risk["score"],

            "verification":
                verification,

            "persistence":
                persistence,

            "lat":
                cluster[
                    "center"
                ]["lat"],

            "lon":
                cluster[
                    "center"
                ]["lon"],

            "count":
                risk["count"],

            "max_frp":
                risk["max_frp"],

            "total_frp":
                risk["total_frp"],

            "observations":
                observations,

            "operational_priority":
                operational[
                    "score"
                ],

            "operational_level":
                operational[
                    "level"
                ],

            "decision":
                operational[
                    "decision"
                ],

            "lifecycle":
                lifecycle,

            "last_seen":
                now_utc().isoformat()

        }

        # ----------------------------------------------------
        # EVENT MEMORY
        # ----------------------------------------------------

        update_event_record(
            state,
            event_id,
            cluster,
            lifecycle,
            operational,
            triggers,
            first_seen
        )

        processed_clusters.append(
            cluster
        )

        print(
            f"   🔥 {event_id} | "
            f"Risk {risk['score']} | "
            f"Verify {verification} | "
            f"Persistence {persistence} | "
            f"Priority {operational['score']} | "
            f"{lifecycle}"
        )

    # ========================================================
    # NATIONAL SITUATION
    # ========================================================

    national = (
        calculate_national_situation(
            processed_clusters
        )
    )

    print(
        f"🏛️ National Situation: "
        f"{national['score']}/100 | "
        f"{national['level']}"
    )

    # ========================================================
    # ALERT DECISION
    # ========================================================

    alert_clusters = []

    for cluster in processed_clusters:

        cid = cluster_id(
            cluster
        )

        operational = cluster[
            "operational"
        ]

        risk = cluster[
            "risk"
        ]

        previous = find_previous_cluster(
            cluster,
            previous_clusters
        )

        should_alert = False

        # ----------------------------------------------------
        # NEW SIGNIFICANT EVENT
        # ----------------------------------------------------

        if previous is None:

            if (
                ALERT_NEW_CLUSTER
                and
                is_significant_new_cluster(
                    cluster
                )
                and
                alert_allowed(
                    cid,
                    state
                )
            ):

                should_alert = True

                print(
                    f"🆕 Significant new event: "
                    f"{cluster['event_id']}"
                )

        # ----------------------------------------------------
        # OPERATIONAL ESCALATION
        # ----------------------------------------------------

        if (
            operational[
                "score"
            ]
            >=
            ESCALATION_PRIORITY
        ):

            if alert_allowed(
                cid,
                state
            ):

                should_alert = True

                print(
                    f"🚨 Operational escalation: "
                    f"{cluster['event_id']}"
                )

        # ----------------------------------------------------
        # TREND ESCALATION
        # ----------------------------------------------------

        if (
            "تصاعد"
            in
            cluster[
                "trend"
            ]
            and
            risk[
                "score"
            ]
            >=
            50
        ):

            if alert_allowed(
                cid,
                state
            ):

                should_alert = True

                print(
                    f"📈 Trend escalation: "
                    f"{cluster['event_id']}"
                )

        if should_alert:

            alert_clusters.append(
                cluster
            )

            mark_alert(
                cid,
                state
            )

    print(
        f"🚨 Alert clusters: "
        f"{len(alert_clusters)}"
    )

    # ========================================================
    # HISTORY
    # ========================================================

    history = state.setdefault(
        "history",
        {}
    )

    for cid, current in (
        current_cluster_state.items()
    ):

        old = history.get(
            cid
        )

        if old:

            historical_observations = int(
                old.get(
                    "historical_observations",
                    0
                )
            ) + 1

        else:

            historical_observations = 1

        current[
            "historical_observations"
        ] = (
            historical_observations
        )

        history[
            cid
        ] = current

    # ========================================================
    # REPORT
    # ========================================================

    send_monitoring_report(
        processed_clusters,
        raw_count,
        len(events),
        stats[
            "outside_saudi"
        ],
        national
    )

    # ========================================================
    # SAVE
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
    # FINAL LOG
    # ========================================================

    print("=" * 70)

    print(
        "🏛️ Government Monitoring Center completed"
    )

    print(
        "📡 Detection analysis completed"
    )

    print(
        "🎯 Operational priority completed"
    )

    print(
        "🧠 Trigger intelligence completed"
    )

    print(
        "🔄 Event lifecycle completed"
    )

    print(
        "📊 National situation completed"
    )

    print(
        "⏱️ Temporal persistence completed"
    )

    print(
        "🧠 Historical memory completed"
    )

    print(
        "🚨 Escalation analysis completed"
    )

    print(
        "💾 State saved successfully"
    )

    print(
        "🤖 Saudi Wildfire Intelligence V5.9.4"
    )

    print(
        "✅ V5.9.4 completed successfully"
    )

    print("=" * 70)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()
