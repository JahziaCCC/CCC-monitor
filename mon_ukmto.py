import hashlib
import requests
import re

def _fp(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:24]

def fetch():
    url = "https://www.ukmto.org/recent-incidents"

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; MonitoringBot/1.0)"
    }

    # ✅ لا توقف النظام لو الموقع منعنا
    try:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        html = r.text
    except Exception:
        return []

    hits = re.findall(r"(UKMTO[^<\\n]{0,180})", html, flags=re.IGNORECASE)
    hits = [re.sub(r"\\s+", " ", h).strip() for h in hits]
    hits = list(dict.fromkeys(hits))

    items = []
    for h in hits[:8]:
        items.append({
            "key": _fp("ukmto|" + h.lower()),
            "section": "marine",
            "title": f"⚓ UKMTO: {h}",
            "link": url,
            "meta": {}
        })

    return items
