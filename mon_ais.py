# mon_ais.py
import os

def get_events():
    key = os.environ.get("AISSTREAM_API_KEY", "")
    base = os.environ.get("AIS_BASE_URL", "")
    api = os.environ.get("AIS_API_KEY", "")

    if not key and not (base and api):
        return [{
            "section": "ais",
            "title": "ℹ️ AIS غير مفعّل: ضع AISSTREAM_API_KEY أو AIS_BASE_URL + AIS_API_KEY."
        }]

    # لاحقاً نضيف الاستعلام الحقيقي
    return []
