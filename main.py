# main.py
import os
from datetime import datetime, timezone, timedelta

# مصادر الرصد
import mon_dust
import mon_gdacs
import mon_fires
import mon_ukmto

# عندك AIS باسم mon_ais_ports.py
import mon_ais_ports

# التقرير الرسمي (الذي ينسّق النص ويرسله للتلقرام)
import report_official


def _utcnow():
    return datetime.now(timezone.utc)


def collect_events(include_ais: bool = True):
    """
    يجمع كل الأحداث من المونيتورز المختلفة.
    """
    events = []

    # 1) الغبار / جودة الهواء
    try:
        events.extend(mon_dust.fetch())
    except Exception as e:
        events.append({
            "section": "dust",
            "title": f"⚠️ خطأ في رصد الغبار: {e}"
        })

    # 2) GDACS
    try:
        events.extend(mon_gdacs.fetch())
    except Exception as e:
        events.append({
            "section": "gdacs",
            "title": f"⚠️ خطأ في GDACS: {e}"
        })

    # 3) FIRMS (🔥 مهم جداً — هذا اللي كان ناقص عندك)
    try:
        events.extend(mon_fires.fetch())
    except Exception as e:
        events.append({
            "section": "fires",
            "title": f"⚠️ خطأ في FIRMS: {e}"
        })

    # 4) UKMTO
    try:
        events.extend(mon_ukmto.fetch())
    except Exception as e:
        events.append({
            "section": "ukmto",
            "title": f"⚠️ خطأ في UKMTO: {e}"
        })

    # 5) AIS (اختياري)
    if include_ais:
        try:
            events.extend(mon_ais_ports.fetch())
        except Exception as e:
            events.append({
                "section": "ais",
                "title": f"⚠️ خطأ في AIS: {e}"
            })

    return events


def run_report(title: str, only_if_new: bool = False, include_ais: bool = True):
    """
    تشغيل التقرير الرسمي وإرساله إلى Telegram
    """
    events = collect_events(include_ais=include_ais)

    # report_official مسؤول عن بناء النص النهائي وإرساله
    report_official.run(
        title=title,
        events=events,
        only_if_new=only_if_new
    )


def main():
    # عنوان التقرير (نفس أسلوبك)
    run_report("📌 تقرير الرصد والتحديث التشغيلي", only_if_new=False, include_ais=True)


if __name__ == "__main__":
    main()
