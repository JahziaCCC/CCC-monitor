import os, json, math, threading, datetime, requests, websocket

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
API_KEY = os.environ["AISSTREAM_API_KEY"]

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
now = datetime.datetime.now(KSA_TZ)

CAPTURE_SECONDS = 600
WAITING_SPEED_KTS = 0.7
PORT_RADIUS_KM = 120

SAUDI_BIG_BOX = [[10.0, 32.0], [32.5, 58.5]]

# سواحل المملكة
KSA_RED_SEA = [[16.0, 34.0], [29.8, 41.8]]
KSA_GULF    = [[24.0, 48.4], [28.9, 52.6]]

# تقييم إقليمي fallback
REG_RED_SEA = [[12.0, 32.0], [30.5, 44.8]]
REG_GULF    = [[21.0, 47.0], [30.5, 56.5]]

# مواقع المملكة الاستراتيجية
KSA_SITES = {
    "ميناء جدة الإسلامي": {"lat": 21.484, "lon": 39.173},
    "ميناء الملك عبدالله (KAEC)": {"lat": 22.523, "lon": 39.089},
    "ميناء ينبع التجاري": {"lat": 24.0665, "lon": 38.0675},
    "ميناء جازان": {"lat": 16.9189, "lon": 42.5573},
    "ميناء ضباء": {"lat": 27.5606, "lon": 35.5440},
    "ميناء نيوم (أوكساچون)": {"lat": 27.730, "lon": 35.310},
    "ميناء الملك عبدالعزيز (الدمام)": {"lat": 26.4410, "lon": 50.1485},
    "ميناء الجبيل التجاري": {"lat": 27.0241, "lon": 49.6793},
    "محطة نفط رأس تنورة": {"lat": 26.6726, "lon": 50.1219},
    "محطة نفط الجعيمة": {"lat": 26.93, "lon": 50.06},
    "محطة نفط تناجيب": {"lat": 27.7948, "lon": 48.8921},
}

# موانئ إقليمية للـ fallback
REGIONAL_PORTS = {
    "ميناء راشد (دبي)": {"lat": 25.270, "lon": 55.275},
    "ميناء جبل علي": {"lat": 24.985, "lon": 55.060},
    "ميناء خورفكان": {"lat": 25.340, "lon": 56.360},
    "ميناء الفجيرة": {"lat": 25.120, "lon": 56.330},
}

def send(msg):
    requests.post(
        f"https://api.telegram.org/bot{BOT}/sendMessage",
        json={"chat_id": CHAT_ID, "text": msg},
        timeout=25
    )

def haversine(lat1, lon1, lat2, lon2):
    R=6371
    p1,p2=math.radians(lat1),math.radians(lat2)
    dlat=math.radians(lat2-lat1)
    dlon=math.radians(lon2-lon1)
    a=math.sin(dlat/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dlon/2)**2
    return 2*R*math.asin(math.sqrt(a))

def in_box(lat,lon,box):
    (a1,o1),(a2,o2)=box
    return min(a1,a2)<=lat<=max(a1,a2) and min(o1,o2)<=lon<=max(o1,o2)

def get_lat_lon(d):
    meta=d.get("MetaData",{})
    if "latitude" in meta and "longitude" in meta:
        return float(meta["latitude"]),float(meta["longitude"])
    msg=d.get("Message",{})
    for _,blk in msg.items():
        if isinstance(blk,dict) and "Latitude" in blk:
            return float(blk["Latitude"]),float(blk["Longitude"])
    raise KeyError

def get_waiting(d):
    msg=d.get("Message",{})
    for _,blk in msg.items():
        if isinstance(blk,dict):
            sog=blk.get("Sog") or blk.get("SOG")
            if sog is not None:
                try:
                    return float(sog)<=WAITING_SPEED_KTS
                except:
                    pass
    return False

def run_stream():
    vessels={}
    opened=False

    def on_open(ws):
        nonlocal opened
        opened=True
        ws.send(json.dumps({
            "APIKey":API_KEY,
            "BoundingBoxes":[SAUDI_BIG_BOX]
        }))

    def on_message(ws,message):
        try:
            d=json.loads(message)
            lat,lon=get_lat_lon(d)
        except:
            return

        m=d.get("MetaData",{}).get("MMSI")
        if not m:
            return

        vessels[str(m)] = {
            "lat":lat,
            "lon":lon,
            "waiting":get_waiting(d)
        }

    ws=websocket.WebSocketApp(
        "wss://stream.aisstream.io/v0/stream",
        on_open=on_open,
        on_message=on_message
    )

    t=threading.Timer(CAPTURE_SECONDS,lambda: ws.close())
    t.start()
    ws.run_forever()
    t.cancel()

    return vessels

def risk_index(total,waiting):
    if total==0:
        return 20
    density=min(total/80,1)*50
    ratio=waiting/total if total else 0
    waiting_score=min(ratio/0.7,1)*50
    return int(min(density+waiting_score,100))

def risk_label(x):
    if x>=80:return "🔴 مرتفع"
    if x>=55:return "🟠 متوسط-مرتفع"
    if x>=30:return "🟡 متوسط"
    return "🟢 منخفض"

# ================= MAIN =================
vessels=run_stream()

ksa={}
regional={}

for m,v in vessels.items():
    lat,lon=v["lat"],v["lon"]

    if in_box(lat,lon,KSA_RED_SEA) or in_box(lat,lon,KSA_GULF):
        ksa[m]=v

    if in_box(lat,lon,REG_RED_SEA) or in_box(lat,lon,REG_GULF):
        regional[m]=v

total_ksa=len(ksa)
waiting_ksa=sum(1 for v in ksa.values() if v["waiting"])

score=risk_index(total_ksa,waiting_ksa)
label=risk_label(score)

# ===== الحركة =====
red=sum(1 for v in ksa.values() if in_box(v["lat"],v["lon"],KSA_RED_SEA))
gulf=sum(1 for v in ksa.values() if in_box(v["lat"],v["lon"],KSA_GULF))

# ===== نشاط الموانئ السعودية =====
site_counts={k:0 for k in KSA_SITES}
for v in ksa.values():
    for s,loc in KSA_SITES.items():
        if haversine(v["lat"],v["lon"],loc["lat"],loc["lon"])<=PORT_RADIUS_KM:
            site_counts[s]+=1

top_sites=sorted(site_counts.items(),key=lambda x:x[1],reverse=True)
top_sites=[x for x in top_sites if x[1]>0][:3]

# ===== fallback إقليمي =====
regional_ports={k:0 for k in REGIONAL_PORTS}
for v in regional.values():
    for p,loc in REGIONAL_PORTS.items():
        if haversine(v["lat"],v["lon"],loc["lat"],loc["lon"])<=200:
            regional_ports[p]+=1

top_reg=sorted(regional_ports.items(),key=lambda x:x[1],reverse=True)
top_reg=[x for x in top_reg if x[1]>0][:2]

# ===== بناء التقرير =====
if total_ksa==0:
    summary = (
        "• لا توجد تغطية AIS كافية داخل سواحل المملكة.\n"
        "• تم تفعيل التقييم الإقليمي للحفاظ على الصورة التشغيلية."
    )
else:
    summary = (
        f"• تم رصد {total_ksa} سفينة داخل سواحل المملكة.\n"
        f"• سفن منتظرة/راسية: {waiting_ksa}."
    )

if top_sites:
    ports_txt="\n".join([f"• {n}: نشاط {'مرتفع' if c>30 else 'متوسط' if c>10 else 'منخفض'} ({c})" for n,c in top_sites])
else:
    ports_txt="• لا توجد كثافة واضحة قرب موانئ المملكة حالياً."

regional_txt=""
if total_ksa==0 and top_reg:
    regional_txt="\n".join([f"• {n}: كثافة {'مرتفعة' if c>50 else 'متوسطة'} ({c})" for n,c in top_reg])

msg=f"""⚓ التقرير البحري الوطني – غرفة العمليات (Smart Executive)
🕒 {now.strftime('%Y-%m-%d %H:%M')} KSA

════════════════════
📊 مؤشر المخاطر البحري:
{score}/100 — {label}

════════════════════
📍 الملخص التنفيذي:
{summary}

════════════════════
🚢 الحركة البحرية (سواحل المملكة):
• البحر الأحمر: {red if total_ksa else "تغطية ضعيفة"}
• الخليج العربي: {gulf if total_ksa else "تغطية ضعيفة"}

════════════════════
⚓ الموانئ والمحطات السعودية:
{ports_txt}
"""

if regional_txt:
    msg += f"""

════════════════════
🌐 التقييم الإقليمي (Fallback):
{regional_txt}
"""

msg += """

════════════════════
🧭 توصية تشغيلية:
• متابعة التحديث القادم.
• عند استمرار ضعف التغطية اعتبر المؤشر استرشادي.
"""

send(msg)
