# mon_gdacs.py

import requests

GDACS_URL = "https://www.gdacs.org/xml/rss.xml"

def get_events():

    try:
        r = requests.get(GDACS_URL, timeout=20)
        r.raise_for_status()

        # لو نجح الاتصال
        return []

    except Exception:
        # يرجع ملاحظة بدل crash
        return [
            {
                "section": "gdacs",
                "title": "ℹ️ ملاحظة: تعذر جلب بيانات GDACS مؤقتاً."
            }
        ]
