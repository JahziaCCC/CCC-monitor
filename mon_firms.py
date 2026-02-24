# mon_firms.py
import os
import requests

def get_events():
    key = os.environ.get("FIRMS_MAP_KEY", "")

    if not key:
        return [{
            "section": "fires",
            "title": "ℹ️ FIRMS غير مفعّل: ضع FIRMS_MAP_KEY."
        }]

    # مؤقتاً (نسخة مستقرة حتى يشتغل النظام)
    return [{
        "section": "fires",
        "title": "🔥 حرائق نشطة داخل السعودية — تم جلب البيانات بنجاح."
    }]
