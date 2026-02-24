# main.py
import os
import datetime

import report_official

def _safe_import(name: str):
    try:
        return __import__(name)
    except Exception as e:
        print(f"[WARN] cannot import {name}: {e}")
        return None


def collect_events(include_ais: bool = True):
    events = []

    mon_gdacs = _safe_import("mon_gdacs")
    if mon_gdacs and hasattr(mon_gdacs, "collect"):
        try:
            gd = mon_gdacs.collect()
            print(f"[DEBUG] gdacs={len(gd)}")
            events.extend(gd)
        except Exception as e:
            print(f"[WARN] mon_gdacs.collect failed: {e}")

    mon_fires = _safe_import("mon_fires")
    if mon_fires and hasattr(mon_fires, "collect"):
        try:
            ff = mon_fires.collect()
            print(f"[DEBUG] fires={len(ff)}")
            events.extend(ff)
        except Exception as e:
            print(f"[WARN] mon_fires.collect failed: {e}")

    mon_ukmto = _safe_import("mon_ukmto")
    if mon_ukmto and hasattr(mon_ukmto, "collect"):
        try:
            uk = mon_ukmto.collect()
            print(f"[DEBUG] ukmto={len(uk)}")
            events.extend(uk)
        except Exception as e:
            print(f"[WARN] mon_ukmto.collect failed: {e}")

    if include_ais:
        mon_ais = _safe_import("mon_ais")
        if mon_ais and hasattr(mon_ais, "collect"):
            try:
                aa = mon_ais.collect()
                print(f"[DEBUG] ais={len(aa)}")
                events.extend(aa)
            except Exception as e:
                print(f"[WARN] mon_ais.collect failed: {e}")

    risk_food = _safe_import("risk_food")
    if risk_food and hasattr(risk_food, "collect"):
        try:
            fd = risk_food.collect()
            print(f"[DEBUG] food={len(fd)}")
            events.extend(fd)
        except Exception as e:
            print(f"[WARN] risk_food.collect failed: {e}")

    print(f"[DEBUG] total events={len(events)}")
    if events:
        print("[DEBUG] sample:", events[0])
    else:
        print("[DEBUG] events is EMPTY")

    return events


def run_report(report_title: str, only_if_new: bool = False, include_ais: bool = True):
    events = collect_events(include_ais=include_ais)

    # دعم الاستدعاء القديم/الجديد
    return report_official.run(
        events=events,
        report_title=report_title,
        only_if_new=only_if_new,
        include_ais=include_ais,
    )


def main():
    print("🚀 CCC Monitor Running...")
    run_report("📄 تقرير الرصد والتحديث التشغيلي", only_if_new=False, include_ais=True)


if __name__ == "__main__":
    main()
