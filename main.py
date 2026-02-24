# main.py
import os
import datetime

import report_official

# استيراد المصادر (إذا ملف ناقص ما يكسر التشغيل)
def _safe_import(name):
    try:
        return __import__(name)
    except Exception:
        return None

mon_gdacs = _safe_import("mon_gdacs")
mon_fires = _safe_import("mon_fires")
mon_ukmto = _safe_import("mon_ukmto")
mon_ais = _safe_import("mon_ais")  # <-- تأكد اسم الملف mon_ais.py

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))

def collect_events(include_ais=True):
    events = []

    if mon_gdacs and hasattr(mon_gdacs, "fetch"):
        events.extend(mon_gdacs.fetch())

    if mon_fires and hasattr(mon_fires, "fetch"):
        events.extend(mon_fires.fetch())

    if mon_ukmto and hasattr(mon_ukmto, "fetch"):
        events.extend(mon_ukmto.fetch())

    if include_ais and mon_ais and hasattr(mon_ais, "fetch"):
        events.extend(mon_ais.fetch())

    return events


def run_report(report_title, only_if_new=True, include_ais=True):
    events = collect_events(include_ais=include_ais)
    return report_official.run(
        report_title=report_title,
        only_if_new=only_if_new,
        include_ais=include_ais,
        events=events
    )


def main():
    # CCC Monitor (التقرير الرئيسي)
    run_report("📄 تقرير الرصد والتحديث التشغيلي", only_if_new=False, include_ais=True)


if __name__ == "__main__":
    main()
