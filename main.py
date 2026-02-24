# main.py
# =========================================
# CCC Monitor - Main Runner
# =========================================

import datetime

# ====== IMPORT MONITORS ======
import mon_gdacs
import mon_ukmto
import mon_ais
import mon_fires
import risk_food

import report_official


# =========================================
# تجميع جميع الأحداث
# =========================================
def collect_events():

    events = []

    # ---------- GDACS ----------
    try:
        events += mon_gdacs.fetch_events()
    except Exception as e:
        events.append({
            "section": "gdacs",
            "title": f"⚠️ خطأ GDACS: {e}"
        })

    # ---------- FIRMS (حرائق) ----------
    try:
        events += mon_fires.fetch_events()
    except Exception as e:
        events.append({
            "section": "fires",
            "title": f"⚠️ خطأ FIRMS: {e}"
        })

    # ---------- UKMTO ----------
    try:
        events += mon_ukmto.fetch_events()
    except Exception as e:
        events.append({
            "section": "ukmto",
            "title": f"⚠️ خطأ UKMTO: {e}"
        })

    # ---------- AIS ----------
    try:
        events += mon_ais.fetch_events()
    except Exception as e:
        events.append({
            "section": "ais",
            "title": f"⚠️ خطأ AIS: {e}"
        })

    # ---------- Food Supply ----------
    try:
        events += risk_food.fetch_events()
    except Exception as e:
        events.append({
            "section": "food",
            "title": f"⚠️ خطأ Food Risk: {e}"
        })

    return events


# =========================================
# MAIN RUN
# =========================================
def main():

    print("🚀 CCC Monitor Running...")

    events = collect_events()

    # إرسال التقرير الرسمي
    report_official.run(events)

    print("✅ Report sent successfully")


# =========================================
if __name__ == "__main__":
    main()
