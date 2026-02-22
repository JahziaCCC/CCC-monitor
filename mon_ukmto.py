import hashlib, requests, re

def _fp(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:24]

def fetch():
    url = "https://www.ukmto.org/recent-incidents"
    r = requests.get(url, timeout=25)
    r.raise_for_status()
    html = r.text

    hits = re.findall(r"(UKMTO[^<\n]{0,180})", html, flags=re.IGNORECASE)
    hits = [re.sub(r"\s+", " ", h).strip() for h in hits]
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
