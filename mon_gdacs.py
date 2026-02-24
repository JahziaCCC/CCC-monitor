# mon_gdacs.py
import os
import requests

GDACS_URL = os.environ.get(
    "GDACS_API_URL",
    "https://www.gdacs.org/gdacsapi/api/events/geteventlist/V2"
)

NEARBY_KEYWORDS = [
    "Saudi", "Saudi Arabia", "KSA",
    "UAE", "United Arab Emirates",
    "Qatar", "Bahrain", "Kuwait", "Oman", "Yemen",
    "Jordan", "Iraq", "Syria", "Iran", "Turkey", "Türkiye",
    "Lebanon", "Palestine",
    "Red Sea", "Gulf"
]

def _is_nearby(text: str) -> bool:
    t = (text or "").lower()
    return any(k.lower() in t for k in NEARBY_KEYWORDS)

def get_events():
    r = requests.get(GDACS_URL, timeout=45)
    r.raise_for_status()
    data = r.json()

    out = []
    for it in (data or []):
        title = (it.get("title") or it.get("eventname") or "").strip()
        if not title:
            continue
        if not _is_nearby(title):
            continue
        out.append({"section": "gdacs", "title": f"🌍 {title}"})

    return out
