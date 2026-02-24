# mon_ukmto.py
# UKMTO Monitor (نسخة بسيطة وآمنة)

import requests

UKMTO_FEED = "https://www.ukmto.org/indian-ocean-vessel-movement-alerts"

def get_events():
    """
    يرجع قائمة أحداث بنفس صيغة باقي المونيتورات
    حتى لو ما فيه بيانات.
    """

    try:
        # حالياً نرجع فقط حالة تشغيل
        # (نقدر نطورها لاحقاً للـ RSS الحقيقي)
        return [
            {
                "section": "ukmto",
                "title": "لا يوجد"
            }
        ]

    except Exception:
        return [
            {
                "section": "ukmto",
                "title": "ℹ️ تعذر جلب بيانات UKMTO مؤقتاً."
            }
        ]
