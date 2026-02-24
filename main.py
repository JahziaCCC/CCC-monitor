# main.py
import sys

import report_official  # التقرير الرئيسي

def _safe_import(name):
    try:
        return __import__(name)
    except Exception as e:
        print(f"[WARN] Could not import {name}: {e}")
        return None

def _collect_events():
    events = []

    # Fires (FIRMS)
    mon_fires = _safe_import("mon_fires")
    if mon_fires and hasattr(mon_fires, "collect"):
        try:
            events.extend(mon_fires.collect())
        except Exception as e:
            print(f"[WARN] mon_fires.collect failed: {e}")

    # UKMTO
    mon_ukmto = _safe_import("mon_ukmto")
    if mon_ukmto and hasattr(mon_ukmto, "collect"):
        try:
            events.extend(mon_ukmto.collect())
        except Exception as e:
            print(f"[WARN] mon_ukmto.collect failed: {e}")

    # AIS
    # انت قلت غيرت الاسم إلى mon_ais.py
    mon_ais = _safe_import("mon_ais")
    if mon_ais and hasattr(mon_ais, "collect"):
        try:
            events.extend(mon_ais.collect())
        except Exception as e:
            print(f"[WARN] mon_ais.collect failed: {e}")

    # Food supply
    risk_food = _safe_import("risk_food")
    if risk_food and hasattr(risk_food, "collect"):
        try:
            events.extend(risk_food.collect())
        except Exception as e:
            print(f"[WARN] risk_food.collect failed: {e}")

    # GDACS
    mon_gdacs = _safe_import("mon_gdacs")
    if mon_gdacs and hasattr(mon_gdacs, "collect"):
        try:
            events.extend(mon_gdacs.collect())
        except Exception as e:
            print(f"[WARN] mon_gdacs.collect failed: {e}")

    return events

def main():
    print("🚀 CCC Monitor Running...")

    events = _collect_events()

    # تقرير رئيسي بدون غبار (الغبار صار تقرير منفصل)
    report_official.run(
        events,
        report_title="📄 تقرير الرصد والتحديث التشغيلي",
        include_ais=True
    )

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[FATAL] {e}")
        sys.exit(1)
