# main.py
import report_official

import mon_gdacs
import mon_fires
import mon_ukmto
import mon_ais  # تأكد اسم الملف mon_ais.py


def collect_events(include_ais=True):
    events = []

    # GDACS
    try:
        events.extend(mon_gdacs.fetch())
    except Exception as e:
        print("[WARN] mon_gdacs failed:", e)

    # FIRMS
    try:
        events.extend(mon_fires.fetch())
    except Exception as e:
        print("[WARN] mon_fires failed:", e)

    # UKMTO
    try:
        events.extend(mon_ukmto.fetch())
    except Exception as e:
        print("[WARN] mon_ukmto failed:", e)

    # AIS
    if include_ais:
        try:
            events.extend(mon_ais.fetch())
        except Exception as e:
            print("[WARN] mon_ais failed:", e)

    return events


def main():
    print("=== CCC Monitor starting ===")

    events = collect_events(include_ais=True)
    print(f"[INFO] Total events collected: {len(events)}")

    report_official.run(
        "📌 تقرير مجدول",
        only_if_new=False,
        include_ais=True,
        events=events
    )

    print("=== CCC Monitor finished ===")


if __name__ == "__main__":
    main()
