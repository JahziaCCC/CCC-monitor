# mon_gdacs.py
import requests
import xml.etree.ElementTree as ET

COLOR_AR = {
    "Green": "🟢 منخفض",
    "Orange": "🟠 مرتفع",
    "Red": "🔴 حرج",
    "Yellow": "🟡 متوسط",
}

def get_events():
    # RSS رسمي
    url = "https://www.gdacs.org/xml/rss.xml"
    r = requests.get(url, timeout=30)
    r.raise_for_status()

    root = ET.fromstring(r.text)
    items = root.findall(".//item")

    out = []
    for it in items[:10]:
        title = (it.findtext("title") or "").strip()
        if not title:
            continue

        # مثال عنوان GDACS: "Green earthquake ..."
        # ناخذ أول كلمة لون:
        first = title.split(" ", 1)[0]
        ar = COLOR_AR.get(first, "")

        # ترجمة بسيطة لأنواع
        t_ar = title
        t_ar = t_ar.replace("earthquake", "زلزال")
        t_ar = t_ar.replace("flood alert", "تنبيه فيضانات")
        t_ar = t_ar.replace("drought", "جفاف")
        t_ar = t_ar.replace("cyclone", "إعصار")

        if ar:
            t_ar = t_ar.replace(first, f"{first} {ar}", 1)

        out.append({"section": "gdacs", "title": f"🌍 {t_ar}"})

    return out if out else [{"section": "gdacs", "title": "لا يوجد أحداث ضمن النطاق حالياً."}]
