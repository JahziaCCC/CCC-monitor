import os
import json
import math
import datetime
import time
import csv
import io
import requests

# ============================================================
# 🔥 Saudi Wildfire Intelligence V5.7
# Advanced Geographic + Temporal Verification Engine
#
# NASA FIRMS + VIIRS
#
# V5.7:
# - Saudi Arabia Polygon Validation
# - VIIRS SNPP + NOAA20
# - Duplicate satellite detection
# - Spatial clustering
# - Temporal persistence
# - Risk Score
# - Verification Score
# - Persistence Score
# - Trend Analysis
# - New / Persistent / Escalating / Declining / Fading
# - Smart Classification
# - Smart Recommendation
# - Alert deduplication
# - Persistent state memory
# - Arabic Telegram alerts
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

STATE_FILE = "wildfire_state_v57.json"


# ============================================================
# 🇸🇦 SAUDI BOUNDING BOX
# يستخدم فقط لتقليل بيانات FIRMS.
# التأكيد النهائي يتم بواسطة Polygon.
# ============================================================

BBOX = (
    34.5,
    16.0,
    55.8,
    32.6
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

TEMPORAL_RADIUS_KM = 5.0

TEMPORAL_LOOKBACK_HOURS = 48

TOP_CLUSTERS = 5


# ============================================================
# ALERT SETTINGS
# ============================================================

ALERT_THRESHOLD = 40

RISK_CHANGE_ALERT = 8

VERIFICATION_CHANGE_ALERT = 10

CLUSTER_MEMORY_HOURS = 72

ALERT_NEW_CLUSTER = True


# ============================================================
# HTTP
# ============================================================

HTTP_HEADERS = {
    "User-Agent":
        "Saudi-Wildfire-Intelligence-V5.7",
    "Accept":
        "text/csv,*/*",
    "Connection":
        "close",
}


# ============================================================
# 🇸🇦 SAUDI ARABIA POLYGON
# (longitude, latitude)
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
        "history": [],
        "last_run": None
    }


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
            []
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


    # --------------------------------------------------------
    # CLEAN HISTORY
    # --------------------------------------------------------

    history = []

    for item in state.get(
        "history",
        []
    ):

        try:

            dt = datetime.datetime.fromisoformat(
                item.get(
                    "timestamp"
                )
            )

            if dt >= cutoff:

                history.append(
                    item
                )

        except Exception:

            pass

    state["history"] = history[
        -1000:
    ]


    state["last_run"] = (
        now_utc().isoformat()
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

    try:

        reader = csv.DictReader(
            io.StringIO(text)
        )

        rows = []

        for row in reader:

            rows.append(
                dict(row)
            )

        return rows

    except Exception as e:

        print(
            f"❌ CSV parser error: {e}"
        )

        return []


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

        if yi == yj:

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
                (yj - yi)
            )
            + xi

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
        # NATURAL
        # ----------------------------------------------------

        if not is_natural_fire(
            row
        ):

            non_natural += 1

            continue


        # ----------------------------------------------------
        # DATETIME
        # ----------------------------------------------------

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
            row.get(
                "confidence"
            )
        )


        satellite = row.get(
            "satellite",
            "VIIRS"
        )


        instrument = row.get(
            "instrument",
            "VIIRS"
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

            "age_hours": age_hours,

            "satellite": satellite,

            "instrument": instrument

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
#
# إزالة التكرار بين الأقمار الصناعية.
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


            spatial_distance = distance_km(

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

                spatial_distance
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
                ] += event[
                    "frp"
                ]


                cluster[
                    "max_frp"
                ] = max(

                    cluster[
                        "max_frp"
                    ],

                    event[
                        "frp"
                    ]

                )


                cluster[
                    "latest"
                ] = max(

                    cluster[
                        "latest"
                    ],

                    event[
                        "datetime"
                    ]

                )


                count = len(
                    cluster[
                        "events"
                    ]
                )


                cluster[
                    "center"
                ][
                    "lat"
                ] = (

                    sum(
                        e["lat"]
                        for e in
                        cluster[
                            "events"
                        ]
                    )
                    /
                    count

                )


                cluster[
                    "center"
                ][
                    "lon"
                ] = (

                    sum(
                        e["lon"]
                        for e in
                        cluster[
                            "events"
                        ]
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
# CLUSTER ID
# ============================================================

def cluster_id(cluster):

    lat = round(
        cluster[
            "center"
        ][
            "lat"
        ],
        2
    )

    lon = round(
        cluster[
            "center"
        ][
            "lon"
        ],
        2
    )

    return f"{lat}_{lon}"


# ============================================================
# TEMPORAL PERSISTENCE
# ============================================================

def calculate_persistence(
    cluster,
    previous
):

    if not previous:

        return 20


    current_lat = cluster[
        "center"
    ][
        "lat"
    ]

    current_lon = cluster[
        "center"
    ][
        "lon"
    ]


    old_lat = previous.get(
        "lat"
    )

    old_lon = previous.get(
        "lon"
    )


    if old_lat is None or old_lon is None:

        return 20


    distance = distance_km(

        current_lat,
        current_lon,

        float(old_lat),
        float(old_lon)

    )


    if distance <= 1:

        return 100

    if distance <= 2:

        return 90

    if distance <= 3:

        return 75

    if distance <= 5:

        return 60

    if distance <= 10:

        return 40

    return 20


# ============================================================
# RISK ENGINE
# ============================================================

def calculate_risk(
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
    # CLUSTER
    # --------------------------------------------------------

    if count >= 10:
        cluster_score = 100

    elif count >= 7:
        cluster_score = 90

    elif count >= 5:
        cluster_score = 80

    elif count >= 3:
        cluster_score = 70

    elif count >= 2:
        cluster_score = 50

    else:
        cluster_score = 20


    # --------------------------------------------------------
    # FINAL
    # --------------------------------------------------------

    risk = (

        frp_score * 0.40

        +

        cluster_score * 0.25

        +

        avg_confidence * 0.20

        +

        persistence_score * 0.15

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
            cluster[
                "total_frp"
            ],

        "count":
            count,

        "persistence":
            persistence_score

    }


# ============================================================
# VERIFICATION SCORE
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


    confidence = (

        sum(
            e["confidence"]
            for e in
            cluster["events"]
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
    # TEMPORAL COMPONENT
    # --------------------------------------------------------

    temporal_component = persistence_score


    verification = (

        cluster_component * 0.35

        +

        frp_component * 0.30

        +

        confidence * 0.20

        +

        temporal_component * 0.15

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

    persistence = risk[
        "persistence"
    ]

    max_frp = risk[
        "max_frp"
    ]


    if (

        score >= 80

        and

        verification >= 75

    ):

        return (

            "حريق محتمل عالي الأولوية",

            "بؤرة حرارية قوية ومتجمعة ومدعومة بأدلة حرارية تستدعي التحقق العاجل"

        )


    if (

        score >= 65

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

        persistence >= 60

    ):

        return (

            "نشاط حراري مستمر",

            "نشاط حراري متكرر مكانيًا ويحتاج إلى التحقق من استمراره"

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
    risk_score,
    verification_score,
    previous
):

    if not previous:

        return (
            "🆕 جديدة",
            "بؤرة جديدة"
        )


    old_risk = float(
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


    risk_difference = (
        risk_score
        -
        old_risk
    )


    verification_difference = (
        verification_score
        -
        old_verification
    )


    if risk_difference >= 8:

        return (

            "📈 تصاعد",

            f"ارتفاع مستوى الخطورة بمقدار "
            f"{risk_difference} نقطة"

        )


    if risk_difference <= -8:

        return (

            "📉 تراجع",

            f"انخفاض مستوى الخطورة بمقدار "
            f"{abs(risk_difference)} نقطة"

        )


    if (
        risk_score >= 60
        and
        old_risk >= 60
    ):

        return (

            "🔄 مستمرة",

            "النشاط الحراري ما زال مستمرًا ضمن النطاق نفسه"

        )


    if verification_difference >= 10:

        return (

            "📈 تصاعد تحقق",

            "تحسن في قوة الأدلة الحرارية"

        )


    return (

        "➡️ مستقرة",

        "مستوى الخطورة مستقر نسبيًا"

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

    persistence = risk[
        "persistence"
    ]


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


    if (

        score >= 65

        and

        "تصاعد" in trend

    ):

        return (

            "🚨 التوصية: رفع مستوى المراقبة "
            "والتحقق العاجل من استمرار النشاط."

        )


    if score >= 65:

        return (

            "⚠️ التوصية: متابعة مكثفة "
            "والتحقق من النشاط."

        )


    if (

        score >= 50

        and

        persistence >= 60

    ):

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
# REGION
# ============================================================

def approximate_region(
    lat,
    lon
):

    if lat >= 30:

        return "الحدود الشمالية / الجوف / تبوك"


    if lat >= 28:

        if lon < 40:

            return "تبوك"

        if lon < 44:

            return "الجوف / الحدود الشمالية"

        return "الحدود الشمالية"


    if lat >= 26:

        if lon < 40:

            return "تبوك / المدينة المنورة"

        if lon < 44:

            return "حائل / القصيم"

        if lon < 48:

            return "القصيم / الرياض"

        return "المنطقة الشرقية"


    if lat >= 24:

        if lon < 40:

            return "المدينة المنورة"

        if lon < 44:

            return "المدينة المنورة / القصيم"

        if lon < 48:

            return "القصيم / الرياض"

        return "المنطقة الشرقية"


    if lat >= 22:

        if lon < 40:

            return "مكة المكرمة"

        if lon < 44:

            return "مكة المكرمة / الرياض"

        if lon < 48:

            return "الرياض / وسط المملكة"

        return "المنطقة الشرقية"


    if lat >= 19:

        if lon < 42:

            return "مكة المكرمة / عسير"

        if lon < 44:

            return "عسير / نجران"

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
# NO FIRE REPORT
# ============================================================

def send_no_fire_report(
    raw_count,
    normalized_count,
    outside_saudi
):

    message = f"""

🟢 رصد حرائق السعودية — V5.7 AI

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
V5.7 Advanced Temporal & Geographic Verification Engine

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

            c["risk"]["persistence"],

            c["risk"]["max_frp"]

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


    _, highest_explanation = (
        classify_cluster(
            highest_risk,
            highest_verification
        )
    )


    message = []


    message.append(
        "🔥 تنبيه حرائق السعودية — V5.7 AI"
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
        highest_explanation
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
            "➡️ مستقرة"
        )


        trend_description = cluster.get(
            "trend_description",
            "مستوى الخطورة مستقر نسبيًا"
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
            f"{risk['persistence']}/100"

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
        "V5.7 Advanced Temporal & Geographic Verification Engine"
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

    print("=" * 70)

    print(
        "🔥 Saudi Wildfire Intelligence V5.7"
    )

    print(
        f"🕒 {now_ksa()}"
    )

    print(
        "🇸🇦 Saudi Polygon Validation ENABLED"
    )

    print(
        "🛰️ Temporal Persistence ENABLED"
    )

    print(
        "🧠 Advanced Verification ENABLED"
    )

    print("=" * 70)


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


    # ========================================================
    # DUPLICATES
    # ========================================================

    before_duplicates = len(
        events
    )


    events = remove_duplicates(
        events
    )


    print(
        f"🔁 Satellite duplicates removed: "
        f"{before_duplicates - len(events)}"
    )


    print(
        f"📍 Unique thermal events: "
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


        seen[uid] = (
            now_utc().isoformat()
        )


        new_events.append(
            event
        )


    print(
        f"🆕 New thermal events: "
        f"{len(new_events)}"
    )


    # ========================================================
    # CLUSTERING
    # ========================================================

    clusters = cluster_events(
        events
    )


    print(
        f"🔥 Spatial clusters: "
        f"{len(clusters)}"
    )


    # ========================================================
    # RISK + VERIFICATION
    # ========================================================

    alert_clusters = []

    current_cluster_state = {}


    for cluster in clusters:

        cid = cluster_id(
            cluster
        )


        previous = (
            previous_clusters.get(
                cid
            )
        )


        persistence_score = (
            calculate_persistence(
                cluster,
                previous
            )
        )


        risk = calculate_risk(

            cluster,

            persistence_score

        )


        verification = (
            calculate_verification_score(

                cluster,

                persistence_score

            )
        )


        cluster[
            "risk"
        ] = risk


        cluster[
            "verification"
        ] = verification


        trend, trend_description = (
            calculate_trend(

                risk["score"],

                verification,

                previous

            )
        )


        cluster[
            "trend"
        ] = trend


        cluster[
            "trend_description"
        ] = trend_description


        current_cluster_state[
            cid
        ] = {

            "risk":
                risk["score"],

            "verification":
                verification,

            "persistence":
                persistence_score,

            "lat":
                cluster[
                    "center"
                ][
                    "lat"
                ],

            "lon":
                cluster[
                    "center"
                ][
                    "lon"
                ],

            "count":
                risk["count"],

            "max_frp":
                risk["max_frp"],

            "total_frp":
                risk["total_frp"],

            "last_seen":
                now_utc().isoformat()

        }


        # ====================================================
        # LOW SINGLE POINT
        # ====================================================

        if (

            risk["score"]
            < ALERT_THRESHOLD

            and

            risk["count"]
            == 1

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
        # NEW
        # ----------------------------------------------------

        if previous is None:

            if ALERT_NEW_CLUSTER:

                should_alert = True

                print(
                    f"🆕 New alert cluster: {cid}"
                )


        else:

            old_risk = float(
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


            risk_difference = (
                risk["score"]
                -
                old_risk
            )


            verification_difference = (
                verification
                -
                old_verification
            )


            # ------------------------------------------------
            # RISK ESCALATION
            # ------------------------------------------------

            if (
                risk_difference
                >= RISK_CHANGE_ALERT
            ):

                should_alert = True

                print(

                    f"📈 Risk escalation: "
                    f"{cid} "
                    f"(+{risk_difference})"

                )


            # ------------------------------------------------
            # VERIFICATION ESCALATION
            # ------------------------------------------------

            elif (
                verification_difference
                >= VERIFICATION_CHANGE_ALERT
            ):

                should_alert = True

                print(

                    f"🧠 Verification escalation: "
                    f"{cid} "
                    f"(+{verification_difference})"

                )


            # ------------------------------------------------
            # LOW → HIGH
            # ------------------------------------------------

            elif (

                old_risk < 60

                and

                risk["score"] >= 60

            ):

                should_alert = True

                print(
                    f"🚨 Risk crossed HIGH: {cid}"
                )


            # ------------------------------------------------
            # HIGH → CRITICAL
            # ------------------------------------------------

            elif (

                old_risk < 80

                and

                risk["score"] >= 80

            ):

                should_alert = True

                print(
                    f"🔴 Risk crossed CRITICAL: {cid}"
                )


        if should_alert:

            alert_clusters.append(
                cluster
            )


    # ========================================================
    # SAVE HISTORY SNAPSHOT
    # ========================================================

    state.setdefault(
        "history",
        []
    )


    state["history"].append({

        "timestamp":
            now_utc().isoformat(),

        "raw":
            raw_count,

        "events":
            len(events),

        "clusters":
            len(clusters),

        "alerts":
            len(alert_clusters),

        "outside_saudi":
            stats["outside_saudi"]

    })


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

    print("=" * 70)

    print(
        "🇸🇦 Saudi boundary validation completed"
    )

    print(
        "🧠 Temporal persistence completed"
    )

    print(
        "🤖 V5.7 Advanced Temporal & Geographic Verification Engine"
    )

    print(
        "✅ V5.7 completed successfully"
    )

    print("=" * 70)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()
