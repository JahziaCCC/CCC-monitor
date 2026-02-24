# mon_ais.py
import os

def get_events():
    """
    إذا ما عندك مفاتيح AIS لا تكسر التشغيل.
    """
    a = os.environ.get("AISSTREAM_API_KEY", "").strip()
    b = os.environ.get("AIS_BASE_URL", "").strip()
    c = os.environ.get("AIS_API_KEY", "").strip()

    if not a and not (b and c):
        return [{
            "section": "ais",
            "title": "ℹ️ AIS غير مفعّل: ضع AISSTREAM_API_KEY أو AIS_BASE_URL + AIS_API_KEY."
        }]

    # هنا مكان ربط مزود AIS لاحقاً
    return []
