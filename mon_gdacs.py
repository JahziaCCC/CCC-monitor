# mon_gdacs.py
import requests

KSA_KEYWORDS = ["Saudi", "Kingdom of Saudi", "Saudi Arabia", "KSA", "السعودية", "المملكة"]

def _ksa_related(text: str) -> bool:
    t = (text or "").lower()
    return any(k.lower() in t for k in KSA_KEYWORDS)

def fetch():
    """
    مصدر بسيط: RSS عام لـ GDACS (قد يختلف حسب ما عندك سابقاً)
    إذا عندك مصدر آخر سابقاً، خله واستفد فقط من فكرة ksa_related.
    """
    try:
        # RSS عام
        url = "https://www.gdacs.org/xml/rss.xml"
        r = requests.get(url, timeout=45)
        r.raise_for_status()
        xml = r.text

        # parsing خفيف بدون مكتبات إضافية: نلتقط titles
        titles = []
        for part in xml.split("<item>")[1:6]:
            if "<title>" in part and "</title>" in part:
                t = part.split("<title>", 1)[1].split("</title>", 1)[0].strip()
                titles.append(t)

        if not titles:
            return [{"section": "gdacs", "title": "- لا يوجد"}]

        out = []
        for t in titles:
            out.append({
                "section": "gdacs",
                "title": f"- 🌍 {t}",
                "ksa_related": _ksa_related(t)
            })
        return out
    except Exception:
        return [{"section": "gdacs", "title": "- لا يوجد"}]
