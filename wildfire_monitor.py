import os
import json
import math
import datetime
import time
import requests

# ============================================================
# 🔥 Saudi Wildfire Intelligence V5.4
# Advanced Intelligent Verification & Alerting Engine
#
# NASA FIRMS + VIIRS
#
# V5.4:
# - تجميع النقاط الحرارية
# - تقييم الخطورة
# - درجة التحقق الذكي
# - تحليل قوة البؤرة
# - تحليل التجمع
# - تحليل الثقة
# - تحليل الاستمرارية
# - تحليل التصاعد
# - تصنيف البؤرة
# - توصية ذكية
# - منع تكرار التنبيهات
# - إدارة ذاكرة البؤر
# - تنبيه عربي بالكامل
# ============================================================

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
FIRMS_KEY = os.environ["FIRMS_API_KEY"]

KSA_TZ = datetime.timezone(
    datetime.timedelta(hours=3)
)

STATE_FILE = "wildfire_state_v54.json"


# ============================================================
# إعدادات الرصد
# ============================================================

BBOX = (
    34.5,   # min longitude
    16.0,   # min latitude
    55.8,   # max longitude
    32.6    # max latitude
)

SOURCES = [
    "VIIRS_SNPP_NRT",
    "VIIRS_NOAA20_NRT",
]

# أقل FRP
MIN_FRP = 3.0

# أقصى عمر للبيانات
MAX_AGE_HOURS = 24

# نصف قطر التجميع
CLUSTER_RADIUS_KM = 2.5

# أقصى فرق زمني داخل البؤرة
CLUSTER_TIME_MINUTES = 180

# عدد البؤر المعروضة
TOP_CLUSTERS = 5


# ============================================================
# إعدادات التنبيه V5.4
# ============================================================

ALERT_THRESHOLD = 40

# مقدار التغير المطلوب لإعادة التنبيه
RISK_CHANGE_ALERT = 8

# ذاكرة البؤرة
CLUSTER_MEMORY_HOURS = 48

# السماح بتنبيه البؤرة الجديدة
ALERT_NEW_CLUSTER = True

# الحد الأدنى لدرجة التحقق
VERIFICATION_THRESHOLD = 55

# ============================================================
# منع الإرسال المتكرر
# ============================================================

# أقل مدة بين تنبيهين لنفس البؤرة
MIN_ALERT_INTERVAL_MINUTES = 60


# ============================================================
# Headers
# ============================================================

HTTP_HEADERS = {
    "User-Agent":
        "Saudi-Wildfire-Intelligence-V5.4",
    "Accept":
        "text/csv,*/*",
    "Connection":
        "close",
}


# ============================================================
# الوقت
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
        "alerts": {},
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
            "alerts",
            {}
        )

        state.setdefault(
            "last_run",
            None
        )

        return state

    except Exception:

        return default_state()


def save_state(state):

    cutoff = (
        now_utc()
        -
        datetime.timedelta(
            hours=CLUSTER_MEMORY_HOURS
        )
    )

    # ========================================================
    # تنظيف الأحداث
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

            if dt >= cutoff:

                cleaned_seen[key] = value

        except Exception:

            pass

    state["seen"] = cleaned_seen

    # ========================================================
    # تنظيف البؤر
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

            if dt >= cutoff:

                cleaned_clusters[key] = value

        except Exception:

            pass

    state["clusters"] = cleaned_clusters

    # ========================================================
    # تنظيف سجل التنبيهات
    # ========================================================

    cleaned_alerts = {}

    for key, value in state.get(
        "alerts",
        {}
    ).items():

        try:

            dt = datetime.datetime.fromisoformat(
                value.get(
                    "last_alert"
                )
            )

            if dt >= cutoff:

                cleaned_alerts[key] = value

        except Exception:

            pass

    state["alerts"] = cleaned_alerts

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
            header[i]:
                columns[i]
            for i in range(
                len(header)
            )
        })

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
        "https://firms.modaps.eosdis.nasa.gov/"
        f"api/area/csv/"
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
# السعودية
# ============================================================

def is_saudi_bbox(
    lat,
    lon
):

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
            math.sqrt(
                1 - a
            )
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

        if not is_natural_fire(
            row
        ):

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

        if (
            age_hours
            >
            MAX_AGE_HOURS
        ):

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

        confidence = (
            confidence_score(
                row.get(
                    "confidence"
                )
            )
        )

        events.append({

            "lat": lat,

            "lon": lon,

            "frp": frp,

            "confidence": confidence,

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

    return events


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

            center = (
                cluster["center"]
            )

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
                        in cluster["events"]
                    )
                    /
                    count
                )

                cluster[
                    "center"
                ]["lon"] = (
                    sum(
                        e["lon"]
                        for e
                        in cluster["events"]
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

def calculate_frp_score(
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

def calculate_cluster_score(
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
# PERSISTENCE SCORE
# ============================================================

def calculate_persistence_score(
    count
):

    if count >= 10:

        return 100

    if count >= 7:

        return 85

    if count >= 5:

        return 75

    if count >= 3:

        return 60

    if count >= 2:

        return 40

    return 20


# ============================================================
# RISK ENGINE
# ============================================================

def calculate_risk(
    cluster
):

    count = len(
        cluster["events"]
    )

    max_frp = (
        cluster["max_frp"]
    )

    total_frp = (
        cluster["total_frp"]
    )

    avg_confidence = (
        sum(
            e["confidence"]
            for e
            in cluster["events"]
        )
        /
        count
    )

    frp_score = (
        calculate_frp_score(
            max_frp
        )
    )

    cluster_score = (
        calculate_cluster_score(
            count
        )
    )

    persistence_score = (
        calculate_persistence_score(
            count
        )
    )

    risk = (
        frp_score * 0.40
        +
        cluster_score * 0.30
        +
        avg_confidence * 0.20
        +
        persistence_score * 0.10
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
            count,

        "frp_score":
            frp_score,

        "cluster_score":
            cluster_score,

        "persistence_score":
            persistence_score
    }


# ============================================================
# VERIFICATION ENGINE V5.4
# ============================================================

def calculate_verification(
    cluster,
    risk,
    previous=None
):

    count = risk["count"]

    max_frp = risk["max_frp"]

    confidence = risk[
        "confidence"
    ]

    # --------------------------------------------------------
    # 1. قوة النشاط الحراري
    # --------------------------------------------------------

    frp_component = (
        risk["frp_score"]
    )

    # --------------------------------------------------------
    # 2. قوة التجمع
    # --------------------------------------------------------

    cluster_component = (
        risk["cluster_score"]
    )

    # --------------------------------------------------------
    # 3. جودة الثقة
    # --------------------------------------------------------

    confidence_component = (
        confidence
    )

    # --------------------------------------------------------
    # 4. الاستمرارية / كثافة النقاط
    # --------------------------------------------------------

    persistence_component = (
        risk["persistence_score"]
    )

    # --------------------------------------------------------
    # 5. التطور
    # --------------------------------------------------------

    trend_component = 50

    if previous:

        old_score = float(
            previous.get(
                "risk",
                0
            )
        )

        current_score = (
            risk["score"]
        )

        difference = (
            current_score
            -
            old_score
        )

        if difference >= 10:

            trend_component = 100

        elif difference >= 5:

            trend_component = 80

        elif difference <= -10:

            trend_component = 30

        elif difference <= -5:

            trend_component = 40

        else:

            trend_component = 60

    # --------------------------------------------------------
    # الدرجة النهائية
    # --------------------------------------------------------

    verification = (

        frp_component * 0.30

        +

        cluster_component * 0.25

        +

        confidence_component * 0.20

        +

        persistence_component * 0.15

        +

        trend_component * 0.10
    )

    verification = round(
        min(
            100,
            max(
                0,
                verification
            )
        )
    )

    # --------------------------------------------------------
    # تصنيف التحقق
    # --------------------------------------------------------

    if verification >= 85:

        verification_level = (
            "تحقق مرتفع جدًا"
        )

    elif verification >= 70:

        verification_level = (
            "تحقق مرتفع"
        )

    elif verification >= 55:

        verification_level = (
            "تحقق متوسط"
        )

    else:

        verification_level = (
            "تحقق منخفض"
        )

    return {

        "score":
            verification,

        "level":
            verification_level,

        "frp":
            frp_component,

        "cluster":
            cluster_component,

        "confidence":
            confidence_component,

        "persistence":
            persistence_component,

        "trend":
            trend_component
    }


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

    verification_score = (
        verification["score"]
    )

    count = risk[
        "count"
    ]

    max_frp = risk[
        "max_frp"
    ]

    # --------------------------------------------------------
    # حرج + تحقق قوي
    # --------------------------------------------------------

    if (
        score >= 80
        and
        verification_score >= 75
    ):

        return (

            "حريق محتمل عالي الأولوية",

            "بؤرة حرارية قوية ومتجمعة "
            "وتستدعي التحقق العاجل"
        )

    # --------------------------------------------------------
    # حرج لكن تحقق أقل
    # --------------------------------------------------------

    if score >= 80:

        return (

            "بؤرة حرارية حرجة",

            "نشاط حراري قوي يستدعي "
            "التحقق قبل اعتبارها حريقًا مؤكدًا"
        )

    # --------------------------------------------------------
    # مرتفع
    # --------------------------------------------------------

    if (
        score >= 65
        and
        count >= 3
    ):

        return (

            "حريق محتمل مرتفع الأولوية",

            "تجمع حراري متعدد النقاط "
            "ويستحق المتابعة"
        )

    # --------------------------------------------------------
    # متوسط
    # --------------------------------------------------------

    if score >= 50:

        return (

            "بؤرة حرارية تحتاج مراقبة",

            "بؤرة حرارية ملحوظة "
            "وتحتاج إلى المتابعة"
        )

    # --------------------------------------------------------
    # FRP قوي
    # --------------------------------------------------------

    if max_frp >= 40:

        return (

            "نقطة حرارية قوية",

            "شدة حرارية مرتفعة ولكن "
            "الأدلة غير كافية لتأكيد حريق"
        )

    return (

        "نقطة حرارية منخفضة الأولوية",

        "نشاط حراري محدود "
        "ولا يستدعي تنبيهًا عاجلًا"
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

    new_score = (
        cluster["risk"]["score"]
    )

    difference = (
        new_score
        -
        old_score
    )

    if difference >= 8:

        return (

            "📈 تصاعد",

            "ارتفاع مستوى الخطورة "
            f"بمقدار {difference} نقطة"
        )

    if difference <= -8:

        return (

            "📉 تراجع",

            "انخفاض مستوى الخطورة "
            f"بمقدار {abs(difference)} نقطة"
        )

    return (

        "➡️ مستقر",

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

    verification_score = (
        verification["score"]
    )

    # --------------------------------------------------------
    # حرج
    # --------------------------------------------------------

    if score >= 80:

        if (
            verification_score >= 75
        ):

            return (
                "🚨 التوصية: متابعة عاجلة "
                "والتحقق من البؤرة ميدانيًا "
                "أو عبر مصدر مرئي إضافي."
            )

        return (
            "🚨 التوصية: رفع مستوى المراقبة "
            "والتحقق من البؤرة عبر مصدر إضافي "
            "قبل اتخاذ إجراء ميداني."
        )

    # --------------------------------------------------------
    # مرتفع
    # --------------------------------------------------------

    if score >= 65:

        if "تصاعد" in trend:

            return (
                "⚠️ التوصية: رفع مستوى المراقبة "
                "والتحقق من استمرار النشاط."
            )

        return (
            "⚠️ التوصية: متابعة مكثفة "
            "والتحقق من النشاط."
        )

    # --------------------------------------------------------
    # متوسط
    # --------------------------------------------------------

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

def cluster_id(
    cluster
):

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
# ============================================================

def approximate_region(
    lat,
    lon
):

    if lat >= 28:

        return "شمال المملكة"

    if (
        lat >= 24
        and
        lon < 44
    ):

        return (
            "المدينة المنورة / "
            "شمال غرب المملكة"
        )

    if (
        lat >= 22
        and
        lon < 48
    ):

        return (
            "الرياض / وسط المملكة"
        )

    if (
        lat < 22
        and
        lon < 44
    ):

        return (
            "جازان / "
            "جنوب غرب المملكة"
        )

    if lon >= 48:

        return "المنطقة الشرقية"

    return (
        "المملكة العربية السعودية"
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
    alerts
):

    previous_alert = alerts.get(
        cid
    )

    if not previous_alert:

        return True

    try:

        last_alert = (
            datetime.datetime.fromisoformat(
                previous_alert[
                    "last_alert"
                ]
            )
        )

        elapsed_minutes = (
            now_utc()
            -
            last_alert
        ).total_seconds() / 60

        return (
            elapsed_minutes
            >=
            MIN_ALERT_INTERVAL_MINUTES
        )

    except Exception:

        return True


# ============================================================
# NO FIRE REPORT
# ============================================================

def send_no_fire_report(
    raw_count,
    normalized_count
):

    message = f"""
🟢 رصد حرائق السعودية — V5.4 AI

🕒 {now_ksa()}

✅ لا توجد بؤر تستدعي التنبيه العاجل حاليًا.

📊 بيانات FIRMS المستلمة: {raw_count}
🧪 النقاط بعد التحليل: {normalized_count}

🧠 محرك التحقق:
V5.4 Advanced Intelligent Verification Engine

🛰️ المصدر:
NASA FIRMS / VIIRS

الحالة:
النظام يعمل بشكل طبيعي

⚠️ المخرجات تمثل بؤرًا حرارية وحريقًا محتملًا وليست تأكيدًا ميدانيًا للحريق.
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
    normalized_count
):

    clusters = sorted(

        clusters,

        key=lambda c: (

            c["risk"]["score"],

            c["verification"]["score"],

            c["risk"]["max_frp"],

            c["risk"]["count"]
        ),

        reverse=True
    )

    top = clusters[
        :TOP_CLUSTERS
    ]

    highest = top[0]

    highest_risk = (
        highest["risk"]
    )

    highest_verification = (
        highest["verification"]
    )

    highest_lat = (
        highest["center"]["lat"]
    )

    highest_lon = (
        highest["center"]["lon"]
    )

    message = []

    message.append(
        "🔥 تنبيه حرائق السعودية — V5.4 AI"
    )

    message.append(
        f"🕒 {now_ksa()}"
    )

    message.append("")

    message.append(
        f"🚨 البؤر التي تستدعي "
        f"المتابعة: {len(clusters)}"
    )

    message.append(
        f"📊 النقاط الحرارية المحللة: "
        f"{normalized_count}"
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
        f"{highest_verification['score']}/100"
    )

    message.append("")

    classification, explanation = (
        classify_cluster(
            highest_risk,
            highest_verification
        )
    )

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

        center = (
            cluster["center"]
        )

        risk = (
            cluster["risk"]
        )

        verification = (
            cluster["verification"]
        )

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

        trend_description = (
            cluster.get(
                "trend_description",
                "مستوى الخطورة مستقر نسبيًا"
            )
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
            f"{lat:.4f}, "
            f"{lon:.4f}"
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
            f"{verification['score']}/100"
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
        "V5.4 Advanced Intelligent Verification Engine"
    )

    message.append("")

    message.append(
        "⚠️ ملاحظة: "
        "المخرجات تمثل بؤرًا حرارية "
        "وحريقًا محتملًا وليست تأكيدًا "
        "ميدانيًا للحريق."
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
        "🔥 Saudi Wildfire Intelligence V5.4"
    )

    print(
        f"🕒 {now_ksa()}"
    )

    print(
        "=" * 70
    )

    state = load_state()

    seen = state.get(
        "seen",
        {}
    )

    previous_clusters = (
        state.get(
            "clusters",
            {}
        )
    )

    alerts = state.get(
        "alerts",
        {}
    )

    all_rows = []

    # ========================================================
    # FIRMS DATA
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

    events = normalize_rows(
        all_rows
    )

    print(
        f"🧪 After filtering: "
        f"{len(events)}"
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
    # CLUSTERING
    # ========================================================

    clusters = cluster_events(
        events
    )

    print(
        f"🔥 Clusters: "
        f"{len(clusters)}"
    )

    # ========================================================
    # RISK + VERIFICATION
    # ========================================================

    alert_clusters = []

    current_cluster_state = {}

    for cluster in clusters:

        # ----------------------------------------------------
        # RISK
        # ----------------------------------------------------

        risk = calculate_risk(
            cluster
        )

        cluster["risk"] = risk

        # ----------------------------------------------------
        # ID
        # ----------------------------------------------------

        cid = cluster_id(
            cluster
        )

        # ----------------------------------------------------
        # PREVIOUS
        # ----------------------------------------------------

        previous = (
            previous_clusters.get(
                cid
            )
        )

        # ----------------------------------------------------
        # TREND
        # ----------------------------------------------------

        trend, trend_description = (
            calculate_trend(
                cluster,
                previous
            )
        )

        cluster["trend"] = (
            trend
        )

        cluster[
            "trend_description"
        ] = (
            trend_description
        )

        # ----------------------------------------------------
        # VERIFICATION
        # ----------------------------------------------------

        verification = (
            calculate_verification(
                cluster,
                risk,
                previous
            )
        )

        cluster[
            "verification"
        ] = verification

        # ----------------------------------------------------
        # STATE
        # ----------------------------------------------------

        current_cluster_state[
            cid
        ] = {

            "risk":
                risk["score"],

            "verification":
                verification["score"],

            "lat":
                cluster["center"]["lat"],

            "lon":
                cluster["center"]["lon"],

            "count":
                risk["count"],

            "max_frp":
                risk["max_frp"],

            "last_seen":
                now_utc().isoformat()
        }

        # ----------------------------------------------------
        # LOW SINGLE POINT
        # ----------------------------------------------------

        if (
            risk["score"]
            <
            ALERT_THRESHOLD
            and
            risk["count"]
            ==
            1
        ):

            print(
                f"🟢 Low cluster ignored: "
                f"{cid} "
                f"{risk['score']}/100"
            )

            continue

        # ----------------------------------------------------
        # VERIFICATION FILTER
        # ----------------------------------------------------

        if (
            risk["score"] < 60
            and
            verification["score"]
            <
            VERIFICATION_THRESHOLD
        ):

            print(
                f"🟢 Low verification cluster: "
                f"{cid} "
                f"Risk={risk['score']} "
                f"Verification="
                f"{verification['score']}"
            )

            continue

        # ----------------------------------------------------
        # ALERT DECISION
        # ----------------------------------------------------

        should_alert = False

        # ----------------------------------------------------
        # NEW CLUSTER
        # ----------------------------------------------------

        if previous is None:

            if ALERT_NEW_CLUSTER:

                should_alert = True

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

            old_verification = float(
                previous.get(
                    "verification",
                    0
                )
            )

            score_difference = (
                risk["score"]
                -
                old_score
            )

            verification_difference = (
                verification["score"]
                -
                old_verification
            )

            # ------------------------------------------------
            # تصاعد الخطورة
            # ------------------------------------------------

            if (
                score_difference
                >=
                RISK_CHANGE_ALERT
            ):

                should_alert = True

                print(
                    f"📈 Escalated cluster: "
                    f"{cid} "
                    f"(+{score_difference})"
                )

            # ------------------------------------------------
            # ارتفاع التحقق
            # ------------------------------------------------

            elif (
                verification_difference
                >=
                RISK_CHANGE_ALERT
            ):

                should_alert = True

                print(
                    f"🧠 Verification increased: "
                    f"{cid} "
                    f"(+{verification_difference})"
                )

            # ------------------------------------------------
            # منخفض -> مرتفع
            # ------------------------------------------------

            elif (
                old_score < 60
                and
                risk["score"] >= 60
            ):

                should_alert = True

                print(
                    f"🚨 Risk level increased: "
                    f"{cid}"
                )

            # ------------------------------------------------
            # مرتفع -> حرج
            # ------------------------------------------------

            elif (
                old_score < 80
                and
                risk["score"] >= 80
            ):

                should_alert = True

                print(
                    f"🔴 Critical escalation: "
                    f"{cid}"
                )

        # ----------------------------------------------------
        # ALERT COOLDOWN
        # ----------------------------------------------------

        if should_alert:

            if not alert_allowed(
                cid,
                alerts
            ):

                print(
                    f"⏳ Alert cooldown active: "
                    f"{cid}"
                )

                should_alert = False

        # ----------------------------------------------------
        # ADD ALERT
        # ----------------------------------------------------

        if should_alert:

            alert_clusters.append(
                cluster
            )

            alerts[cid] = {

                "last_alert":
                    now_utc().isoformat(),

                "risk":
                    risk["score"],

                "verification":
                    verification["score"]
            }

    # ========================================================
    # ALERT COUNT
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
            len(events)
        )

    else:

        send_no_fire_report(
            raw_count,
            len(events)
        )

    # ========================================================
    # SAVE STATE
    # ========================================================

    state["seen"] = seen

    state[
        "clusters"
    ] = current_cluster_state

    state[
        "alerts"
    ] = alerts

    save_state(
        state
    )

    print(
        "=" * 70
    )

    print(
        "✅ V5.4 completed successfully"
    )

    print(
        "=" * 70
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()
