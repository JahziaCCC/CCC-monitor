# mon_gdacs.py
import requests

GDACS_URL = "https://www.gdacs.org/xml/rss.xml"


def collect():
    try:
        r = requests.get(GDACS_URL, timeout=30)
        r.raise_for_status()
        xml = r.text

        # استخراج بسيط جداً من RSS (بدون مكتبات إضافية)
        items = xml.split("<item>")[1:]
        out = []
        for it in items[:8]:
            title = _between(it, "<title>", "</title>")
            if title:
                title = title.replace("&gt;", ">").replace("&lt;", "<").strip()
                out.append({"section": "gdacs", "title": f"🌍 {title}"})

        return out if out else [{"section": "gdacs", "title": "- لا يوجد"}]
    except Exception:
        return [{"section": "gdacs", "title": "- لا يوجد"}]


def _between(text, a, b):
    try:
        i = text.index(a) + len(a)
        j = text.index(b, i)
        return text[i:j]
    except Exception:
        return ""
