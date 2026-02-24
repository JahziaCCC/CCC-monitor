# main.py
import os

import report_official
import mon_gdacs
import mon_fires
import mon_ukmto
import mon_ais
import risk_food

def collect_events(include_ais: bool = True):
    events = []
    events.extend(risk_food.fetch())
    events.extend(mon_gdacs.fetch())
    events.extend(mon_fires.fetch())
    events.extend(mon_ukmto.fetch())
    if include_ais:
        events.extend(mon_ais.fetch())
    return events

def run_report(report_title: str, only_if_new: bool = False, include_ais: bool = True):
    events = collect_events(include_ais=include_ais)
    return report_official.run(
        report_title,
        events=events,
        only_if_new=only_if_new,
        include_ais=include_ais
    )

def main():
    # defaults
    report_title = os.environ.get("REPORT_TITLE", "📌 تقرير مجدول")
    only_if_new = os.environ.get("ONLY_IF_NEW", "0") == "1"
    include_ais = os.environ.get("INCLUDE_AIS", "1") == "1"

    run_report(report_title, only_if_new=only_if_new, include_ais=include_ais)

if __name__ == "__main__":
    main()
