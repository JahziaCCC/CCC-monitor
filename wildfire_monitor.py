import os
import json
import math
import datetime
import time
import requests


# ============================================================
# 🔥 Saudi Wildfire Intelligence V5.9.2
# GOVERNMENT MONITORING CENTER ENGINE
#
# NASA FIRMS + VIIRS
#
# V5.9.2
# ------------------------------------------------------------
# يحافظ على وظائف V5.8 / V5.9 / V5.9.1:
#
# - Saudi Arabia Polygon Validation
# - BBOX pre-filter
# - Natural fire filtering
# - FRP filtering
# - Duplicate protection
# - Spatial clustering
# - Temporal persistence
# - Historical cluster matching
# - Persistent historical memory
# - Risk Score
# - Verification Score
# - Persistence Score
# - Trend Analysis
# - Smart Classification
# - Smart Recommendation
# - Alert escalation logic
# - Alert cooldown
# - Duplicate alert protection
# - New cluster intelligence
# - Strong single-point detection
# - Arabic executive Telegram alerts
#
# NEW V5.9.2:
# - Government Monitoring Center Layer
# - National Operational Status
# - Operational Priority Score
# - Operational Decision
# - Event Lifecycle
# - Stable Event ID
# - Situation Awareness
# - Escalation Level
# - Event Age
# - First Seen / Last Seen
# - Active / Monitoring / Escalated / Declining / Stable
# - National Situation Summary
# - Improved executive Telegram report
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
# STATE FILE
# ============================================================

STATE_FILE = "wildfire_state_v592.json"


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

ALERT_NEW_CLUSTER = True

ALERT_COOLDOWN_HOURS = 6

NEW_CLUSTER_MIN_RISK = 50

NEW_CLUSTER_MIN_COUNT = 2

NEW_CLUSTER_STRONG_FRP = 40


# ============================================================
# TEMPORAL SETTINGS
# ============================================================

TEMPORAL_MATCH_RADIUS_KM = 5.0

PERSISTENCE_WINDOW_HOURS = 72

PERSISTENCE_TIME_WEIGHT = 0.55

PERSISTENCE_COUNT_WEIGHT = 0.45


# ============================================================
# HISTORICAL MEMORY
# ============================================================

HISTORY_MEMORY_HOURS = 168

MAX_HISTORY_CLUSTERS = 500


# ============================================================
# GOVERNMENT MONITORING CENTER
# ============================================================

OPERATIONAL_MONITOR_THRESHOLD = 35

OPERATIONAL_HIGH_THRESHOLD = 60

OPERATIONAL_CRITICAL_THRESHOLD = 80

ESCALATION_RISK_THRESHOLD = 60

ESCALATION_VERIFICATION_THRESHOLD = 65

ESCALATION_PERSISTENCE_THRESHOLD = 50

EVENT_ACTIVE_HOURS = 24

EVENT_DECLINING_RISK_DROP = 8

EVENT_STABLE_CHANGE = 8


# ============================================================
# HTTP HEADERS
# ============================================================

HTTP_HEADERS = {
    "User-Agent":
        "Saudi-Wildfire-Intelligence-V5.9.2",

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

        "history": {},

        "last_run": None,

        "alerts": {},

        "events": {},

        "center": {}

    }


# ============================================================
# LOAD STATE
# ============================================================

def load_state():

    if not os.path.exists(
        STATE_FILE
    ):

        return default_state()


    try:

        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            state = json.load(f)


        if not isinstance(
            state,
            dict
        ):

            return default_state()


        state.setdefault(
            "seen",
            {}
        )

        state.setdefault(
            "clusters",
            {}
        )

        state.setdefault(
            "history",
            {}
        )

        state.setdefault(
            "alerts",
            {}
        )

        state.setdefault(
            "events",
            {}
        )

        state.setdefault(
            "center",
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
        now
        -
        datetime.timedelta(
            hours=CLUSTER_MEMORY_HOURS
        )
    )

    history_cutoff = (
        now
        -
        datetime.timedelta(
            hours=HISTORY_MEMORY_HOURS
        )
    )


    # ========================================================
    # CLEAN SEEN
    # ========================================================

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

                cleaned_seen[
                    key
                ] = value


        except Exception:

            pass


    state[
        "seen"
    ] = cleaned_seen


    # ========================================================
    # CLEAN CURRENT CLUSTERS
    # ========================================================

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

                cleaned_clusters[
                    key
                ] = value


        except Exception:

            pass


    state[
        "clusters"
    ] = cleaned_clusters


    # ========================================================
    # CLEAN HISTORICAL MEMORY
    # ========================================================

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

                cleaned_history[
                    key
                ] = value


        except Exception:

            pass


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


    state[
        "history"
    ] = cleaned_history


    # ========================================================
    # CLEAN ALERT MEMORY
    # ========================================================

    cleaned_alerts = {}


    alert_cutoff = (
        now
        -
        datetime.timedelta(
            hours=HISTORY_MEMORY_HOURS
        )
    )


    for key, value in state.get(
        "alerts",
        {}
    ).items():

        try:

            dt = datetime.datetime.fromisoformat(
                value
            )


            if dt >= alert_cutoff:

                cleaned_alerts[
                    key
                ] = value


        except Exception:

            pass


    state[
        "alerts"
    ] = cleaned_alerts


    # ========================================================
    # CLEAN EVENTS
    # ========================================================

    cleaned_events = {}


    event_cutoff = (
        now
        -
        datetime.timedelta(
            hours=HISTORY_MEMORY_HOURS
        )
    )


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


            if dt >= event_cutoff:

                cleaned_events[
                    key
                ] = value


        except Exception:

            pass


    state[
        "events"
    ] = cleaned_events


    state[
        "last_run"
    ] = now.isoformat()


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

        "chat_id":
            CHAT_ID,

        "text":
            text,

        "disable_web_page_preview":
            True

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

            header[i]:
                columns[i]

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
                xj - xi
            )
            *
            (
                y - yi
            )
            /
            (
                yj - yi
            )
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


    lat1_rad = math.radians(
        lat1
    )

    lat2_rad = math.radians(
        lat2
    )


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

            current_time
            -
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

            "lat":
                lat,

            "lon":
                lon,

            "frp":
                frp,

            "confidence":
                confidence,

            "date":
                row.get(
                    "acq_date"
                ),

            "time":
                row.get(
                    "acq_time"
                ),

            "datetime":
                acquisition,

            "age_hours":
                age_hours

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
                ].append(
                    event
                )


                cluster[
                    "total_frp"
                ] += event[
                    "frp"
                ]


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
                        for e in cluster["events"]
                    )
                    /
                    count

                )


                cluster[
                    "center"
                ]["lon"] = (

                    sum(
                        e["lon"]
                        for e in cluster["events"]
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

def frp_score_value(max_frp):

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

def cluster_score_value(count):

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


    previous_last_seen_raw = previous.get(
        "last_seen"
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


    current_time = now_utc()


    elapsed_hours = (

        current_time
        -
        previous_last_seen

    ).total_seconds() / 3600


    if elapsed_hours < 0:

        elapsed_hours = 0


    if elapsed_hours > PERSISTENCE_WINDOW_HOURS:

        return 20


    recency = max(

        0,

        100
        -
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
# RISK ENGINE
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
            for e in cluster["events"]
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
            for e in cluster["events"]
        )

        /

        count

    )


    cluster_component = cluster_score_value(
        count
    )


    frp_component = frp_score_value(
        max_frp
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


    return f"{lat}_{lon}"


# ============================================================
# EVENT ID
# ============================================================

def generate_event_id(cluster):

    lat = cluster["center"]["lat"]

    lon = cluster["center"]["lon"]

    today = now_utc().strftime(
        "%Y%m%d"
    )


    lat_code = str(
        abs(int(round(lat * 10)))
    ).zfill(4)


    lon_code = str(
        abs(int(round(lon * 10)))
    ).zfill(4)


    return (
        f"KSA-WF-{today}-"
        f"{lat_code}-"
        f"{lon_code}"
    )


# ============================================================
# HISTORICAL MATCH
# ============================================================

def find_previous_cluster(
    cluster,
    previous_clusters
):

    current_lat = cluster[
        "center"
    ]["lat"]

    current_lon = cluster[
        "center"
    ]["lon"]

    current_time = now_utc()

    best_match = None

    best_distance = None


    for previous in previous_clusters.values():

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


        if age_hours > CLUSTER_MEMORY_HOURS:

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


        if distance > TEMPORAL_MATCH_RADIUS_KM:

            continue


        if (
            best_distance is None
            or
            distance < best_distance
        ):

            best_distance = distance

            best_match = previous


    return best_match


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
    ]["score"]


    difference = (
        new_score
        -
        old_score
    )


    if difference >= RISK_CHANGE_ALERT:

        return (

            "📈 تصاعد",

            f"ارتفاع مستوى الخطورة بمقدار "
            f"{difference} نقطة"

        )


    if difference <= -RISK_CHANGE_ALERT:

        return (

            "📉 تراجع",

            f"انخفاض مستوى الخطورة بمقدار "
            f"{abs(difference)} نقطة"

        )


    return (

        "➡️ مستقر",

        "مستوى الخطورة مستقر نسبيًا"

    )


# ============================================================
# EVENT LIFECYCLE
# ============================================================

def determine_event_lifecycle(
    cluster,
    previous
):

    risk = cluster["risk"]

    score = risk["score"]

    verification = cluster["verification"]

    persistence = cluster["persistence"]


    if previous is None:

        if (
            score >= 80
            and
            verification >= 75
        ):

            return (
                "🚨 تصعيد",
                "تصعيد فوري"
            )


        if (
            score >= 60
            or
            verification >= 65
        ):

            return (
                "⚠️ يحتاج تحقق",
                "يحتاج تحقق إضافي"
            )


        if score >= 40:

            return (
                "👁️ مراقبة",
                "مراقبة أولية"
            )


        return (
            "🆕 جديد",
            "حدث جديد منخفض الأولوية"
        )


    old_score = float(
        previous.get(
            "risk",
            0
        )
    )


    difference = score - old_score


    if (
        score >= ESCALATION_RISK_THRESHOLD
        and
        verification >= ESCALATION_VERIFICATION_THRESHOLD
        and
        persistence >= ESCALATION_PERSISTENCE_THRESHOLD
    ):

        return (
            "🚨 تصعيد",
            "حدث يستوفي مؤشرات التصعيد التشغيلي"
        )


    if difference >= EVENT_STABLE_CHANGE:

        return (
            "📈 متصاعد",
            "ارتفاع ملحوظ في النشاط"
        )


    if difference <= -EVENT_DECLINING_RISK_DROP:

        return (
            "📉 متراجع",
            "انخفاض ملحوظ في النشاط"
        )


    if score >= 40:

        return (
            "👁️ مراقبة",
            "حدث نشط تحت المراقبة"
        )


    return (
        "➡️ مستقر",
        "نشاط مستقر منخفض الأولوية"
    )


# ============================================================
# OPERATIONAL PRIORITY
# ============================================================

def calculate_operational_priority(
    risk,
    verification,
    persistence,
    trend,
    lifecycle
):

    risk_score = risk["score"]


    priority = (

        risk_score * 0.45

        +

        verification * 0.25

        +

        persistence * 0.15

    )


    # تأثير الاتجاه

    if "تصاعد" in trend:

        priority += 10


    elif "تراجع" in trend:

        priority -= 5


    # تأثير دورة الحياة

    if "تصعيد" in lifecycle:

        priority += 10


    elif "يحتاج تحقق" in lifecycle:

        priority += 5


    priority = round(
        max(
            0,
            min(
                100,
                priority
            )
        )
    )


    if priority >= 80:

        level = "حرج"

        emoji = "🔴"

        decision = "🚨 تصعيد فوري"

        description = (
            "يتطلب رفع مستوى الاستجابة والتحقق العاجل"
        )


    elif priority >= 60:

        level = "مرتفع"

        emoji = "🟠"

        decision = "⚠️ متابعة مكثفة"

        description = (
            "يستدعي متابعة مكثفة والتحقق من التطور"
        )


    elif priority >= 40:

        level = "متوسط"

        emoji = "🟡"

        decision = "👁️ مراقبة"

        description = (
            "مراقبة الحدث دون تصعيد فوري"
        )


    else:

        level = "منخفض"

        emoji = "🟢"

        decision = "🟢 روتينية"

        description = (
            "لا توجد حاجة لتصعيد تشغيلي حاليًا"
        )


    return {

        "score":
            priority,

        "level":
            level,

        "emoji":
            emoji,

        "decision":
            decision,

        "description":
            description

    }


# ============================================================
# RECOMMENDATION
# ============================================================

def recommendation(
    risk,
    verification,
    persistence,
    trend
):

    score = risk["score"]


    if (
        score >= 80
        and
        verification >= 75
    ):

        return (
            "🚨 التوصية: متابعة عاجلة "
            "والتحقق من البؤرة ميدانيًا "
            "أو عبر مصدر مرئي إضافي."
        )


    if score >= 65:

        if "تصاعد" in trend:

            return (
                "🚨 التوصية: رفع مستوى المراقبة "
                "والتحقق من استمرار وتصاعد النشاط."
            )


        if persistence >= 50:

            return (
                "⚠️ التوصية: متابعة مكثفة "
                "والتحقق من استمرارية النشاط."
            )


        return (
            "⚠️ التوصية: متابعة مكثفة "
            "والتحقق من النشاط."
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
# REGION
# ============================================================

def approximate_region(
    lat,
    lon
):

    if lat >= 29:

        return "الحدود الشمالية / الجوف / تبوك"


    if lat >= 27:

        if lon < 42:

            return "تبوك / شمال غرب المملكة"

        return "حائل / الحدود الشمالية"


    if lat >= 24:

        if lon < 42:

            return "المدينة المنورة / شمال غرب المملكة"


        if lon < 48:

            return "القصيم / الرياض"


        return "المنطقة الشرقية"


    if lat >= 22:

        if lon < 42:

            return "مكة المكرمة / المدينة المنورة"


        if lon < 48:

            return "الرياض / وسط المملكة"


        return "المنطقة الشرقية"


    if lat >= 18:

        if lon < 44:

            return "عسير / جازان"


        if lon < 48:

            return "نجران"


        return "المنطقة الشرقية"


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


    last_alert_raw = alerts.get(
        cid
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


    if elapsed >= ALERT_COOLDOWN_HOURS:

        return True


    print(

        f"⏸️ Alert cooldown active: "
        f"{cid} | "
        f"{elapsed:.1f}h"

    )


    return False


# ============================================================
# MARK ALERT
# ============================================================

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
    ][
        cid
    ] = now_utc().isoformat()


# ============================================================
# NEW CLUSTER DECISION
# ============================================================

def is_significant_new_cluster(
    cluster
):

    risk = cluster[
        "risk"
    ]


    if risk["score"] >= NEW_CLUSTER_MIN_RISK:

        return True


    if (
        risk["count"] >= NEW_CLUSTER_MIN_COUNT
        and
        risk["max_frp"] >= 20
    ):

        return True


    if (
        risk["count"] == 1
        and
        risk["max_frp"] >= NEW_CLUSTER_STRONG_FRP
    ):

        return True


    return False


# ============================================================
# BUILD EVENT STATE
# ============================================================

def build_event_state(
    cluster,
    previous,
    cid
):

    risk = cluster["risk"]

    verification = cluster["verification"]

    persistence = cluster["persistence"]

    trend = cluster["trend"]

    lifecycle, lifecycle_description = (
        determine_event_lifecycle(
            cluster,
            previous
        )
    )


    operational = (
        calculate_operational_priority(

            risk,

            verification,

            persistence,

            trend,

            lifecycle

        )
    )


    old_event = None


    if previous:

        old_event = previous.get(
            "event_id"
        )


    event_id = (
        old_event
        if old_event
        else
        generate_event_id(
            cluster
        )
    )


    if previous:

        first_seen = previous.get(
            "first_seen",
            now_utc().isoformat()
        )


        observations = int(

            previous.get(
                "observations",
                1
            )

        ) + 1


    else:

        first_seen = now_utc().isoformat()

        observations = 1


    return {

        "event_id":
            event_id,

        "cluster_id":
            cid,

        "lat":
            cluster["center"]["lat"],

        "lon":
            cluster["center"]["lon"],

        "region":
            approximate_region(

                cluster["center"]["lat"],

                cluster["center"]["lon"]

            ),

        "risk":
            risk["score"],

        "risk_level":
            risk["level"],

        "verification":
            verification,

        "persistence":
            persistence,

        "trend":
            trend,

        "trend_description":
            cluster["trend_description"],

        "lifecycle":
            lifecycle,

        "lifecycle_description":
            lifecycle_description,

        "operational_priority":
            operational["score"],

        "operational_level":
            operational["level"],

        "operational_emoji":
            operational["emoji"],

        "operational_decision":
            operational["decision"],

        "operational_description":
            operational["description"],

        "count":
            risk["count"],

        "max_frp":
            risk["max_frp"],

        "total_frp":
            risk["total_frp"],

        "observations":
            observations,

        "first_seen":
            first_seen,

        "last_seen":
            now_utc().isoformat()

    }


# ============================================================
# NATIONAL CENTER STATUS
# ============================================================

def calculate_center_status(
    event_states
):

    if not event_states:

        return {

            "level":
                "طبيعي",

            "emoji":
                "🟢",

            "score":
                0,

            "description":
                "لا توجد أحداث نشطة تستدعي التصعيد"

        }


    priorities = [

        float(
            e.get(
                "operational_priority",
                0
            )
        )

        for e in event_states.values()

    ]


    risks = [

        float(
            e.get(
                "risk",
                0
            )
        )

        for e in event_states.values()

    ]


    highest_priority = max(
        priorities
    )

    highest_risk = max(
        risks
    )


    critical = sum(

        1

        for e in event_states.values()

        if e.get(
            "operational_level"
        ) == "حرج"

    )


    high = sum(

        1

        for e in event_states.values()

        if e.get(
            "operational_level"
        ) == "مرتفع"

    )


    if critical > 0:

        return {

            "level":
                "حالة حرجة",

            "emoji":
                "🔴",

            "score":
                round(
                    highest_priority
                ),

            "description":
                "يوجد حدث ذو أولوية حرجة ويتطلب التصعيد"

        }


    if (
        high >= 2
        or
        highest_priority >= OPERATIONAL_HIGH_THRESHOLD
    ):

        return {

            "level":
                "نشاط مرتفع",

            "emoji":
                "🟠",

            "score":
                round(
                    highest_priority
                ),

            "description":
                "نشاط حراري مرتفع يستدعي متابعة مكثفة"

        }


    if (
        highest_priority >= OPERATIONAL_MONITOR_THRESHOLD
        or
        highest_risk >= 40
    ):

        return {

            "level":
                "تحت المراقبة",

            "emoji":
                "🟡",

            "score":
                round(
                    highest_priority
                ),

            "description":
                "توجد أحداث حرارية تحت المراقبة دون تصعيد فوري"

        }


    return {

        "level":
            "طبيعي",

        "emoji":
            "🟢",

        "score":
            round(
                highest_priority
            ),

        "description":
            "النشاط الحالي منخفض الأولوية"

    }


# ============================================================
# SITUATION SUMMARY
# ============================================================

def situation_summary(
    event_states
):

    critical = 0
    high = 0
    medium = 0
    low = 0

    new = 0
    rising = 0
    declining = 0

    escalated = 0


    for event in event_states.values():

        level = event.get(
            "operational_level"
        )


        if level == "حرج":
            critical += 1

        elif level == "مرتفع":
            high += 1

        elif level == "متوسط":
            medium += 1

        else:
            low += 1


        trend = event.get(
            "trend",
            ""
        )


        lifecycle = event.get(
            "lifecycle",
            ""
        )


        if "جديدة" in trend:
            new += 1

        elif "تصاعد" in trend:
            rising += 1

        elif "تراجع" in trend:
            declining += 1


        if "تصعيد" in lifecycle:
            escalated += 1


    return {

        "critical":
            critical,

        "high":
            high,

        "medium":
            medium,

        "low":
            low,

        "new":
            new,

        "rising":
            rising,

        "declining":
            declining,

        "escalated":
            escalated

    }


# ============================================================
# GOVERNMENT CENTER REPORT
# ============================================================

def send_government_report(
    event_states,
    raw_count,
    normalized_count,
    outside_saudi,
    center_status
):

    events = list(
        event_states.values()
    )


    events.sort(

        key=lambda e: (

            e.get(
                "operational_priority",
                0
            ),

            e.get(
                "risk",
                0
            ),

            e.get(
                "verification",
                0
            )

        ),

        reverse=True

    )


    top = events[
        :TOP_CLUSTERS
    ]


    summary = situation_summary(
        event_states
    )


    message = []


    message.append(
        "🔥 مركز مراقبة حرائق السعودية — V5.9.2"
    )


    message.append(
        f"🕒 {now_ksa()}"
    )


    message.append("")


    # ========================================================
    # CENTER STATUS
    # ========================================================

    message.append(
        "🏛️ الحالة التشغيلية:"
    )


    message.append(

        f"{center_status['emoji']} "
        f"{center_status['level']}"

    )


    message.append(

        f"🎯 مؤشر المركز: "
        f"{center_status['score']}/100"

    )


    message.append(
        center_status[
            "description"
        ]
    )


    message.append("")


    # ========================================================
    # NATIONAL SITUATION
    # ========================================================

    message.append(
        "📡 الموقف الوطني:"
    )


    message.append(

        f"🚨 أحداث نشطة: "
        f"{len(events)}"

    )


    message.append(

        f"🔴 حرجة: {summary['critical']} | "
        f"🟠 عالية: {summary['high']} | "
        f"🟡 متوسطة: {summary['medium']} | "
        f"🟢 منخفضة: {summary['low']}"

    )


    message.append(

        f"🆕 جديدة: {summary['new']} | "
        f"📈 متصاعدة: {summary['rising']} | "
        f"📉 متراجعة: {summary['declining']}"

    )


    message.append(

        f"🚨 حالات تصعيد: "
        f"{summary['escalated']}"

    )


    message.append("")


    # ========================================================
    # TOP PRIORITY
    # ========================================================

    if top:

        highest = top[0]


        message.append(
            "🎯 أعلى أولوية تشغيلية:"
        )


        message.append(

            f"{highest['operational_emoji']} "
            f"{highest['operational_level']} — "
            f"{highest['operational_priority']}/100"

        )


        message.append(

            f"{highest['operational_decision']}"

        )


        message.append(

            highest[
                "operational_description"
            ]

        )


        message.append("")


        message.append(
            "🚨 أعلى مستوى خطورة:"
        )


        message.append(

            f"{risk_emoji_from_score(highest['risk'])} "
            f"{risk_level_from_score(highest['risk'])} — "
            f"{highest['risk']}/100"

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


        message.append("")


    # ========================================================
    # EVENTS
    # ========================================================

    message.append(
        "📌 أبرز الأحداث:"
    )


    for index, event in enumerate(
        top,
        start=1
    ):

        message.append("")


        message.append(

            f"{index}) "
            f"{event['operational_emoji']} "
            f"أولوية {event['operational_level']} — "
            f"{event['operational_priority']}/100"

        )


        message.append(

            f"🆔 الحدث: "
            f"{event['event_id']}"

        )


        message.append(

            f"🚨 الخطورة: "
            f"{risk_emoji_from_score(event['risk'])} "
            f"{risk_level_from_score(event['risk'])} — "
            f"{event['risk']}/100"

        )


        message.append(

            f"📍 الموقع: "
            f"{event['lat']:.4f}, "
            f"{event['lon']:.4f}"

        )


        message.append(

            f"🗺️ النطاق: "
            f"{event['region']}"

        )


        message.append(

            f"🔥 عدد النقاط: "
            f"{event['count']}"

        )


        message.append(

            f"⚡ أعلى شدة: "
            f"{event['max_frp']:.1f} MW"

        )


        message.append(

            f"📊 إجمالي FRP: "
            f"{event['total_frp']:.1f} MW"

        )


        confidence_text = (
            "عالية"
            if event["verification"] >= 75
            else
            "متوسطة"
            if event["verification"] >= 50
            else
            "منخفضة"
        )


        message.append(

            f"🎯 التحقق: "
            f"{confidence_text}"

        )


        message.append(

            f"🤖 التصنيف: "
            f"{operational_classification(event)}"

        )


        message.append(

            f"📈 الاتجاه: "
            f"{event['trend']}"

        )


        message.append(

            f"🔄 الحالة: "
            f"{event['lifecycle']}"

        )


        message.append(

            f"🧠 درجة التحقق: "
            f"{event['verification']}/100"

        )


        message.append(

            f"⏱️ الاستمرارية: "
            f"{event['persistence']}/100"

        )


        message.append(

            f"📊 الرصد المتكرر: "
            f"{event['observations']}"

        )


        message.append(

            f"🏛️ القرار: "
            f"{event['operational_decision']}"

        )


        message.append(

            f"📝 الإجراء: "
            f"{event['operational_description']}"

        )


        message.append(

            f"📍 الخريطة: "
            f"{google_maps(event['lat'], event['lon'])}"

        )


    message.append("")


    # ========================================================
    # DATA QUALITY
    # ========================================================

    message.append(
        "📊 بيانات الرصد:"
    )


    message.append(
        f"FIRMS: {raw_count}"
    )


    message.append(
        f"بعد التحليل: {normalized_count}"
    )


    message.append(

        f"خارج حدود المملكة: "
        f"{outside_saudi}"

    )


    message.append("")


    # ========================================================
    # ENGINE
    # ========================================================

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
        "Saudi Wildfire Intelligence V5.9.2"
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
        "🇸🇦 التحقق الجغرافي:"
    )


    message.append(
        "Saudi Arabia Boundary Polygon"
    )


    message.append("")


    message.append(
        "🧠 الذكاء التشغيلي:"
    )


    message.append(
        "Risk + Verification + Persistence + Trend + Operational Priority"
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
# HELPER: RISK LEVEL
# ============================================================

def risk_level_from_score(score):

    if score >= 80:
        return "حرج"

    if score >= 60:
        return "مرتفع"

    if score >= 40:
        return "متوسط"

    return "منخفض"


def risk_emoji_from_score(score):

    if score >= 80:
        return "🔴"

    if score >= 60:
        return "🟠"

    if score >= 40:
        return "🟡"

    return "🟢"


# ============================================================
# OPERATIONAL CLASSIFICATION
# ============================================================

def operational_classification(event):

    risk = event["risk"]

    verification = event["verification"]

    persistence = event["persistence"]


    if (
        risk >= 80
        and
        verification >= 75
    ):

        return "حريق محتمل عالي الأولوية"


    if (
        risk >= 65
        and
        persistence >= 50
    ):

        return "حريق محتمل مرتفع الأولوية"


    if risk >= 50:

        return "بؤرة حرارية تحتاج مراقبة"


    return "نشاط حراري منخفض الأولوية"


# ============================================================
# NO EVENT REPORT
# ============================================================

def send_no_event_report(
    raw_count,
    normalized_count,
    outside_saudi
):

    message = f"""

🟢 مركز مراقبة حرائق السعودية — V5.9.2

🕒 {now_ksa()}

🏛️ الحالة التشغيلية:
🟢 طبيعي

🎯 مؤشر المركز:
0/100

📡 الموقف الوطني:
🚨 أحداث نشطة: 0

🟢 لا توجد بؤر تستدعي التنبيه أو التصعيد التشغيلي حاليًا.

📊 بيانات الرصد:
FIRMS: {raw_count}
بعد التحليل: {normalized_count}
خارج حدود المملكة: {outside_saudi}

🛰️ المصدر:
NASA FIRMS / VIIRS

🤖 محرك التحليل:
Saudi Wildfire Intelligence V5.9.2

🏛️ طبقة مركز المراقبة:
Government Monitoring Center Engine

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
# UPDATE HISTORICAL MEMORY
# ============================================================

def update_history(
    state,
    current_cluster_state
):

    history = state.setdefault(
        "history",
        {}
    )


    for cid, current in current_cluster_state.items():

        previous_history = history.get(
            cid
        )


        if previous_history:

            observations = int(

                previous_history.get(
                    "observations",
                    0
                )

            ) + 1


            current[
                "historical_observations"
            ] = observations


        else:

            current[
                "historical_observations"
            ] = 1


        history[
            cid
        ] = current


    state[
        "history"
    ] = history


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 75)

    print(
        "🔥 Saudi Wildfire Intelligence V5.9.2"
    )

    print(
        "🏛️ GOVERNMENT MONITORING CENTER ENGINE"
    )

    print(
        f"🕒 {now_ksa()}"
    )

    print("=" * 75)


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
        f"📊 Total FIRMS rows: {raw_count}"
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
        f"🔥 Current clusters: "
        f"{len(clusters)}"
    )


    # ========================================================
    # ANALYSIS
    # ========================================================

    alert_clusters = []

    current_cluster_state = {}

    current_event_states = {}


    for cluster in clusters:

        # ----------------------------------------------------
        # HISTORICAL MATCH
        # ----------------------------------------------------

        previous = find_previous_cluster(

            cluster,

            previous_clusters

        )


        # ----------------------------------------------------
        # PERSISTENCE
        # ----------------------------------------------------

        persistence = calculate_persistence(

            cluster,

            previous

        )


        cluster[
            "persistence"
        ] = persistence


        # ----------------------------------------------------
        # RISK
        # ----------------------------------------------------

        risk = calculate_risk(

            cluster,

            persistence

        )


        cluster[
            "risk"
        ] = risk


        # ----------------------------------------------------
        # VERIFICATION
        # ----------------------------------------------------

        verification = (
            calculate_verification_score(

                cluster,

                persistence

            )
        )


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
        # ID
        # ----------------------------------------------------

        cid = cluster_id(
            cluster
        )


        # ----------------------------------------------------
        # EVENT STATE
        # ----------------------------------------------------

        event_state = build_event_state(

            cluster,

            previous,

            cid

        )


        current_event_states[
            cid
        ] = event_state


        current_cluster_state[
            cid
        ] = event_state


        print(

            f"   🔥 {event_state['event_id']} | "
            f"Risk {risk['score']} | "
            f"Verify {verification} | "
            f"Persistence {persistence} | "
            f"Priority {event_state['operational_priority']} | "
            f"{event_state['lifecycle']}"

        )


        # ====================================================
        # LOW SINGLE POINT
        # ====================================================

        if (

            risk["score"]
            < ALERT_THRESHOLD

            and

            risk["count"]
            == 1

            and

            persistence
            < 50

            and

            risk["max_frp"]
            < NEW_CLUSTER_STRONG_FRP

        ):

            print(

                f"🟢 Low cluster ignored: "
                f"{cid} "
                f"{risk['score']}/100"

            )

            continue


        # ====================================================
        # ALERT DECISION
        # ====================================================

        should_alert = False


        # ----------------------------------------------------
        # NEW CLUSTER
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

                    f"🆕 Significant new alert cluster: "
                    f"{cid}"

                )


        # ----------------------------------------------------
        # EXISTING CLUSTER
        # ----------------------------------------------------

        else:

            old_score = float(

                previous.get(
                    "risk",
                    0
                )

            )


            old_persistence = float(

                previous.get(
                    "persistence",
                    20
                )

            )


            score_difference = (

                risk["score"]
                -
                old_score

            )


            persistence_difference = (

                persistence
                -
                old_persistence

            )


            # ----------------------------------------------
            # RISK ESCALATION
            # ----------------------------------------------

            if (
                score_difference
                >= RISK_CHANGE_ALERT
            ):

                if alert_allowed(
                    cid,
                    state
                ):

                    should_alert = True

                    print(

                        f"📈 Escalated cluster: "
                        f"{cid} "
                        f"(+{score_difference})"

                    )


            # ----------------------------------------------
            # LOW → HIGH
            # ----------------------------------------------

            elif (

                old_score < 60

                and

                risk["score"] >= 60

            ):

                if alert_allowed(
                    cid,
                    state
                ):

                    should_alert = True

                    print(
                        f"🚨 Risk level increased: "
                        f"{cid}"
                    )


            # ----------------------------------------------
            # HIGH → CRITICAL
            # ----------------------------------------------

            elif (

                old_score < 80

                and

                risk["score"] >= 80

            ):

                if alert_allowed(
                    cid,
                    state
                ):

                    should_alert = True

                    print(
                        f"🔴 Critical escalation: "
                        f"{cid}"
                    )


            # ----------------------------------------------
            # PERSISTENCE ESCALATION
            # ----------------------------------------------

            elif (

                persistence_difference >= 15

                and

                risk["score"] >= 50

            ):

                if alert_allowed(
                    cid,
                    state
                ):

                    should_alert = True

                    print(

                        f"⏱️ Persistence increased: "
                        f"{cid} "
                        f"(+{persistence_difference})"

                    )


            # ----------------------------------------------
            # TEMPORAL ESCALATION
            # ----------------------------------------------

            elif "تصاعد" in trend:

                if alert_allowed(
                    cid,
                    state
                ):

                    should_alert = True

                    print(
                        f"📈 Temporal escalation: "
                        f"{cid}"
                    )


        # ====================================================
        # ADD ALERT
        # ====================================================

        if should_alert:

            alert_clusters.append(
                event_state
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
    # UPDATE HISTORY
    # ========================================================

    update_history(

        state,

        current_cluster_state

    )


    # ========================================================
    # CENTER STATUS
    # ========================================================

    center_status = calculate_center_status(
        current_event_states
    )


    state[
        "center"
    ] = {

        "status":
            center_status["level"],

        "score":
            center_status["score"],

        "last_update":
            now_utc().isoformat()

    }


    print(
        f"🏛️ Center Status: "
        f"{center_status['emoji']} "
        f"{center_status['level']} "
        f"{center_status['score']}/100"
    )


    # ========================================================
    # REPORT
    # ========================================================

    if current_event_states:

        send_government_report(

            current_event_states,

            raw_count,

            len(events),

            stats["outside_saudi"],

            center_status

        )

    else:

        send_no_event_report(

            raw_count,

            len(events),

            stats["outside_saudi"]

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


    state[
        "events"
    ] = current_event_states


    save_state(
        state
    )


    # ========================================================
    # FINAL LOG
    # ========================================================

    print("=" * 75)

    print(
        "🇸🇦 Saudi boundary validation completed"
    )

    print(
        "⏱️ Temporal persistence analysis completed"
    )

    print(
        "🧠 Historical cluster matching completed"
    )

    print(
        "💾 Persistent historical memory completed"
    )

    print(
        "🚨 Alert cooldown completed"
    )

    print(
        "📈 Escalation analysis completed"
    )

    print(
        "🏛️ Government operational intelligence completed"
    )

    print(
        "🎯 Operational priority analysis completed"
    )

    print(
        "🆔 Event lifecycle management completed"
    )

    print(
        "📡 National situation awareness completed"
    )

    print(
        "🤖 V5.9.2 Government Monitoring Center Engine"
    )

    print(
        "✅ V5.9.2 completed successfully"
    )

    print("=" * 75)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()
