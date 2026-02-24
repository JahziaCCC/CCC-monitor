# main.py
import datetime

# ===== Import monitors =====
import mon_dust
import mon_gdacs
import mon_fires
import mon_ukmto
import mon_ais   # ← تأكد الاسم كذا

import report_official


# ==========================
# Collect all events
# ==========================
def collect_events(include_ais=True):

    events = []

    # ---- Dust / PM10 ----
    try:
        events.extend(mon_dust.fetch())
    except Exception as e:
        print("[WARN] mon_dust failed:", e)

    # ---- GDACS ----
    try:
        events.extend(mon_gdacs.fetch())
    except Exception as e:
        print("[WARN] mon_gdacs failed:", e)

    # ---- FIRMS fires ----
    try:
        events.extend(mon_fires.fetch())
    except Exception as e:
        print("[WARN] mon_fires failed:", e)

    # ---- UKMTO ----
    try:
        events.extend(mon_ukmto.fetch())
    except Exception as e:
        print("[WARN] mon_ukmto failed:", e)

    # ---- AIS ----
    if include_ais:
        try:
            events.extend(mon_ais.fetch())
        except Exception as e:
            print("[WARN] mon_ais failed:", e)

    return events


# ==========================
# Main runner
# ==========================
def main():

    print("=== CCC Monitor starting ===")

    events = collect_events(include_ais=True)

    print(f"[INFO] Total events collected: {len(events)}")

    # IMPORTANT:
    # pass events to report_official.run
    report_official.run(
        "📌 تقرير مجدول",
        only_if_new=False,
        include_ais=True,
        events=events
    )

    print("=== CCC Monitor finished ===")


# ==========================
if __name__ == "__main__":
    main()
