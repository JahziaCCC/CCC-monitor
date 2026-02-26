import os, json, math, threading, datetime, requests, websocket

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
API_KEY = os.environ["AISSTREAM_API_KEY"]

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
now = datetime.datetime.now(KSA_TZ)

CAPTURE_SECONDS = 600
WAITING_SPEED_KTS = 0.7
PORT_RADIUS_KM = 120  # قرب الميناء/المحطة (تشغيلياً)

# صندوق التقاط واسع (لضمان وصول دفق)
SAUDI_BIG_BOX = [[10.0, 32.0], [32.5, 58.5]]

# ممرات “سواحل المملكة فقط” (لتفادي احتساب دبي/الجوار ضمن مؤشرات السعودية)
KSA_RED_SEA = [[16.0, 34.0], [29.8, 41.8]]
KSA_GULF    = [[24.0, 48.4], [28.9, 52.6]]

# =========================
# موانئ المملكة الاستراتيجية + محطات النفط الرئيسية
# (إحداثيات تشغيلية تقريبية كافية للتصنيف)
# =========================
KSA_SITES = {
    # البحر الأحمر
    "ميناء جدة الإسلامي": {"lat": 21.484, "lon": 39.173, "type": "port"},
    "ميناء الملك عبدالله (KAEC)": {"lat": 22.523, "lon": 39.089, "type": "port"},
    "ميناء ينبع التجاري": {"lat": 24.0665, "lon": 38.0675, "type": "port"},
    "ميناء جازان": {"lat": 16.9189, "lon": 42.5573, "type": "port"},
    "ميناء ضباء": {"lat": 27.5606, "lon": 35.5440, "type": "port"},
    "ميناء نيوم (أوكساچون)": {"lat": 27.730, "lon": 35.310, "type": "port"},

    # الخليج العربي
    "ميناء الملك عبدالعزيز (الدمام)": {"lat": 26.4410, "lon": 50.1485, "type": "port"},
    "ميناء الجبيل التجاري": {"lat": 27.0241, "lon": 49.6793, "type": "port"},
    "ميناء رأس الخير": {"lat": 27.115, "lon": 49.230, "type": "port"},

    # محطات النفط
    "محطة نفط رأس تنورة": {"lat": 26.6726, "lon": 50.1219, "type": "oil"},
    "محطة نفط الجعيمة (Juaymah)": {"lat": 26.93, "lon": 50.06, "type": "oil"},
    "محطة نفط تناجيب (Tanajib)": {"lat": 27.7948, "lon": 48.8921, "type": "oil"},
}

def send(msg: str):
    requests.post(
        f"https://api.telegram.org/bot{BOT}/sendMessage",
        json={"chat_id": CHAT_ID, "text": msg},
        timeout=25
    )

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def in_box(lat, lon, box):
    (a1, o1), (a2, o2) = box
    return (min(a1, a2) <= lat <= max(a1, a2)) and (min(o1, o2) <= lon <= max(o1, o2))

def get_lat_lon(d):
    meta = d.get("MetaData") or d.get("Metadata") or {}
    lat = meta.get("latitude") or meta.get("Latitude") or meta.get("lat")
    lon = meta.get("longitude") or meta.get("Longitude") or meta.get("lon")
    if lat is not None and lon is not None:
        lat = float(lat); lon = float(lon)
    else:
        msg = d.get("Message", {})
        lat = lon = None
        for _, blk in msg.items():
            if isinstance(blk, dict) and "Latitude" in blk and "Longitude" in blk:
                lat = float(blk["Latitude"]); lon = float(blk["Longitude"])
                break
        if lat is None or lon is None:
            raise KeyError

    # تصحيح محتمل لتبديل lat/lon
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        if (-90 <= lon <= 90 and -180 <= lat <= 180):
            lat, lon = lon, lat
        else:
            raise KeyError
    return lat, lon

def get_waiting(d):
    msg = d.get("Message", {})
    for _, blk in msg.items():
        if isinstance(blk, dict):
            sog = blk.get("Sog") or blk.get("SOG") or blk.get("SpeedOverGround")
            if sog is not None:
                try:
                    return float(sog) <= WAITING_SPEED_KTS
                except:
                    pass
    return False

def run_stream():
    vessels = {}
    opened = False

    def on_open(ws):
        nonlocal opened
        opened = True
        ws.send(json.dumps({
            "APIKey": API_KEY,
            "BoundingBoxes": [SAUDI_BIG_BOX]
        }))

    def on_message(ws, message):
        try:
            d = json.loads(message)
            lat, lon = get_lat_lon(d)
        except:
            return

        meta = d.get("MetaData") or d.get("Metadata") or {}
        mmsi = meta.get("MMSI") or meta.get("mmsi")
        if not mmsi:
            return

        vessels[str(mmsi)] = {
            "lat": lat,
            "lon": lon,
            "waiting": get_waiting(d)
        }

    ws = websocket.WebSocketApp(
        "wss://stream.aisstream.io/v0/stream",
        on_open=on_open,
        on_message=on_message
    )

    t = threading.Timer(CAPTURE_SECONDS, lambda: ws.close())
    t.start()
    ws.run_forever(ping_interval=20, ping_timeout=10)
    t.cancel()

    return vessels, opened

def clamp(x, a, b):
    return max(a, min(b, x))

def risk_index(total_ksa, waiting_ksa):
    """
    مؤشر مخاطر بحري "خاص بسواحل المملكة" فقط.
    إذا مافيه تغطية داخل سواحل المملكة: نعطي مؤشر منخفض/توثيقي بدل ما نطلع رقم مضلل.
    """
    if total_ksa <= 0:
        return 20

    density = 50.0 * clamp(total_ksa / 80.0, 0.0, 1.0)          # 0..50
    ratio = waiting_ksa / total_ksa if total_ksa else 0.0
    waiting_score = 50.0 * clamp(ratio / 0.70, 0.0, 1.0)         # 0..50

    score = int(round(density + waiting_score))
    return int(clamp(score, 0, 100))

def risk_label(score):
    if score >= 80: return "🔴 مرتفع"
    if score >= 55: return "🟠 متوسط-مرتفع"
    if score >= 30: return "🟡 متوسط"
    return "🟢 منخفض"

def activity_level(n):
    if n >= 30: return "🔴 مرتفع"
    if n >= 12: return "🟠 متوسط"
    if n >= 4:  return "🟡 محدود"
    return "🟢 منخفض"

# =========================
# MAIN
# =========================
vessels, opened = run_stream()

# فلترة سفن “سواحل المملكة فقط”
ksa_vessels = {}
for m, v in vessels.items():
    lat, lon = v["lat"], v["lon"]
    if in_box(lat, lon, KSA_RED_SEA) or in_box(lat, lon, KSA_GULF):
        ksa_vessels[m] = v

total_all = len(vessels)
total_ksa = len(ksa_vessels)
waiting_ksa = sum(1 for v in ksa_vessels.values() if v["waiting"])

# تقسيم البحر الأحمر/الخليج داخل السعودية
ksa_red = 0
ksa_gulf = 0
for v in ksa_vessels.values():
    if in_box(v["lat"], v["lon"], KSA_RED_SEA): ksa_red += 1
    if in_box(v["lat"], v["lon"], KSA_GULF): ksa_gulf += 1

# نشاط قرب المواقع الاستراتيجية (موانئ ومحطات نفط)
site_counts = {name: {"total": 0, "waiting": 0} for name in KSA_SITES.keys()}
for v in ksa_vessels.values():
    for name, s in KSA_SITES.items():
        d = haversine(v["lat"], v["lon"], s["lat"], s["lon"])
        if d <= PORT_RADIUS_KM:
            site_counts[name]["total"] += 1
            if v["waiting"]:
                site_counts[name]["waiting"] += 1

# ترتيب أعلى 5 مواقع
ranked = sorted(site_counts.items(), key=lambda x: (x[1]["total"], x[1]["waiting"]), reverse=True)
top_sites = [(n, d["total"], d["waiting"], KSA_SITES[n]["type"]) for n, d in ranked if d["total"] > 0][:5]

# مؤشر المخاطر
score = risk_index(total_ksa, waiting_ksa)
label = risk_label(score)

# ملخص تنفيذي
if total_ksa == 0:
    exec_summary = (
        "• لا توجد تغطية AIS كافية داخل سواحل المملكة في نافذة الالتقاط الحالية.\n"
        "• تم رصد حركة ضمن النطاق العام، لكن ليست ضمن ممرات سواحل المملكة."
    )
else:
    exec_summary = (
        f"• تم رصد {total_ksa} سفينة ضمن سواحل المملكة.\n"
        f"• سفن منتظرة/راسية: {waiting_ksa}."
    )

# أهم المواقع
if not top_sites:
    sites_block = "• لا توجد كثافة واضحة قرب موانئ/محطات المملكة ضمن النافذة الحالية."
else:
    lines = []
    for name, t, w, typ in top_sites:
        tag = "🛢️" if typ == "oil" else "⚓"
        lines.append(f"{tag} {name}: {activity_level(t)} (إجمالي {t} | انتظار/رسو {w})")
    sites_block = "\n".join(lines)

msg = f"""⚓ التقرير البحري الوطني – غرفة العمليات (نسخة A)
🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA

════════════════════
📊 مؤشر المخاطر البحري (سواحل المملكة):
{score}/100 — {label}

════════════════════
📍 الملخص التنفيذي:
{exec_summary}

════════════════════
🚢 الحركة البحرية داخل سواحل المملكة:
• البحر الأحمر: {ksa_red if total_ksa else "تغطية ضعيفة"}
• الخليج العربي: {ksa_gulf if total_ksa else "تغطية ضعيفة"}

════════════════════
⚓ الموانئ والمحطات الاستراتيجية (ضمن {PORT_RADIUS_KM} كم):
{sites_block}

════════════════════
🧭 توصية تشغيلية:
• متابعة التحديث القادم.
• عند استمرار ضعف التغطية: اعتبر المؤشر “استرشادي” وليس قياسًا كاملًا.
"""

send(msg)
