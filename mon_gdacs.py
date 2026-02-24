# mon_gdacs.py
import requests
import xml.etree.ElementTree as ET

COLOR_AR = {
    "Green": "🟢 منخفض",
    "Orange": "🟠 مرتفع",
    "Red": "🔴 حرج",
    "Yellow": "🟡 متوسط",
}

def _clean_title(title):
    """
    يحذف اللون الإنجليزي من البداية ويضيف العربي فقط
    """
    parts = title.split(" ", 1)

    if len(parts) < 2:
        return title

    color = parts[0]
    rest = parts[1]

    ar_color = COLOR_AR.get(color)

    if ar_color:
        return f"{ar_color} {rest}"

    return title


def _translate_basic(text):
    """
    ترجمة بسيطة لأنواع الأحداث
    """
    text = text.replace("earthquake", "زلزال")
    text = text.replace("flood alert", "تنبيه فيضانات")
    text = text.replace("forest fire notification", "تنبيه حرائق غابات")
    text = text.replace("drought", "جفاف")
    text = text.replace("cyclone", "إعصار")
    return text


def get_events():

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

        title = _clean_title(title)
        title = _translate_basic(title)

        out.append({
            "section": "gdacs",
            "title": f"🌍 {title}"
        })

    if not out:
        return [{
            "section": "gdacs",
            "title": "لا يوجد أحداث ضمن النطاق حالياً."
        }]

    return out
