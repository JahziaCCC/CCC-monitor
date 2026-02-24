# mon_gdacs.py
import requests
import xml.etree.ElementTree as ET

# ترجمة اللون + تخزين severity
COLOR_AR = {
    "Green": "🟢 منخفض",
    "Yellow": "🟡 متوسط",
    "Orange": "🟠 مرتفع",
    "Red": "🔴 حرج",
}

def _detect_event_type(text: str) -> str:
    t = (text or "").lower()
    if "earthquake" in t:
        return "earthquake"
    if "flood" in t:
        return "flood"
    if "drought" in t:
        return "drought"
    if "cyclone" in t or "storm" in t:
        return "cyclone"
    if "volcano" in t or "eruption" in t:
        return "volcano"
    if "landslide" in t:
        return "landslide"
    if "wildfire" in t or "forest fire" in t:
        return "wildfire"
    return "other"

def _clean_title_and_extract_color(title: str):
    """
    GDACS title غالباً يبدأ بـ: Green / Orange / Red / Yellow
    نرجع: (color, rest_title)
    """
    parts = (title or "").strip().split(" ", 1)
    if len(parts) == 2 and parts[0] in COLOR_AR:
        return parts[0], parts[1].strip()
    return None, (title or "").strip()

def _translate_basic(text: str) -> str:
    # ترجمة بسيطة (اختياري)
    x = text
    x = x.replace("earthquake", "زلزال")
    x = x.replace("flood alert", "تنبيه فيضانات")
    x = x.replace("forest fire notification", "تنبيه حرائق غابات")
    x = x.replace("drought", "جفاف")
    x = x.replace("cyclone", "إعصار")
    return x

def get_events(limit=10):
    url = "https://www.gdacs.org/xml/rss.xml"
    r = requests.get(url, timeout=30)
    r.raise_for_status()

    root = ET.fromstring(r.text)
    items = root.findall(".//item")

    out = []
    for it in items[:limit]:
        raw_title = (it.findtext("title") or "").strip()
        if not raw_title:
            continue

        color, rest = _clean_title_and_extract_color(raw_title)
        severity = color or "Green"  # افتراضي
        ar_color = COLOR_AR.get(severity, "🟢 منخفض")

        # نص العرض (نظيف)
        display = f"{ar_color} {rest}"
        display = _translate_basic(display)

        event_type = _detect_event_type(rest)

        out.append({
            "section": "gdacs",
            "title": f"🌍 {display}",
            "severity": severity,        # Green/Yellow/Orange/Red
            "event_type": event_type,    # earthquake/flood/drought/...
        })

    if not out:
        return [{
            "section": "gdacs",
            "title": "لا يوجد أحداث ضمن النطاق حالياً.",
            "severity": "Green",
            "event_type": "other",
        }]

    return out
