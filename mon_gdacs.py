# mon_gdacs.py
import requests

GDACS_URL = "https://www.gdacs.org/xml/rss.xml"

def get_events():
    try:
        r = requests.get(GDACS_URL, timeout=20)
        r.raise_for_status()

        # حالياً نخليه بسيط: إذا نجح الاتصال وما تبغى تفاصيل = رجّع []
        # وإذا تبغى تفاصيل لاحقاً نضيف parsing RSS
        return []

    except Exception as e:
        return [{
            "section": "gdacs",
            "title": f"ℹ️ ملاحظة: تعذر جلب بيانات GDACS/الكوارث الطبيعية مؤقتاً. ({type(e).__name__})"
        }]
