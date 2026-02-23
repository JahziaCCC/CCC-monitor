# main.py
import os
from datetime import datetime, timezone

# مصادر الرصد
import mon_dust
import mon_gdacs
import mon_fires
import mon_ukmto
import mon_ais  # ✅ اسمك الحالي

# التقرير الرسمي (يبني النص ويرسله لتلقرام)
import report_official


def collect_events(include_ais: bool = True):
    """
    يجمع الأحداث من كل المصادر بدون ما يوقف التشغيل لو مصدر تعطل.
    """
    events = []

    # 1) الغبار / جودة الهواء
    try:
        events.extend(mon_dust.fetch())
    except Exception as e:
        events.append({"section": "dust", "title": f"⚠️ خطأ في رصد الغبار: {e}"})

    # 2) GDACS
    try:
        events.extend(mon_gdacs.fetch())
    except Exception as e:
        events.append({"section": "gdacs", "title": f"⚠️ خطأ في GDACS: {e}"})

    # 3) FIRMS
    try:
        events.extend(mon_fires.fetch())
    except Exception as e:
        events.append({"section": "fires", "title": f"⚠️ خطأ في FIRMS: {e}"})

    # 4) UKMTO
    try:
        events.extend(mon_ukmto.fetch())
    except Exception as e:
        events.append({"section": "ukmto", "title": f"⚠️ خطأ في UKMTO: {e}"})

    # 5) AIS
    if include_ais:
        try:
            events.extend(mon_ais.fetch())
        except Exception as e:
            events.append({"section": "ais", "title": f"⚠️ خطأ في AIS: {e}"})

    return events


def main():
    # ✅ هذا هو تشغيل التقرير الرسمي وإرساله للتلقرام
    title = "📌 تقرير الرصد والتحديث التشغيلي"
    events = collect_events(include_ais=True)

    report_official.run(
        title=title,
        events=events,
        only_if_new=False
    )


if __name__ == "__main__":
    main()
