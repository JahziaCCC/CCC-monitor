# main.py
import mon_dust
import mon_gdacs
import mon_fires
import mon_ukmto
import mon_ais  # ✅ اسمك الحالي

import report_official


def collect_events(include_ais: bool = True):
    events = []

    try:
        events.extend(mon_dust.fetch())
    except Exception as e:
        events.append({"section": "dust", "title": f"⚠️ خطأ في رصد الغبار: {e}"})

    try:
        events.extend(mon_gdacs.fetch())
    except Exception as e:
        events.append({"section": "gdacs", "title": f"⚠️ خطأ في GDACS: {e}"})

    try:
        events.extend(mon_fires.fetch())
    except Exception as e:
        events.append({"section": "fires", "title": f"⚠️ خطأ في FIRMS: {e}"})

    try:
        events.extend(mon_ukmto.fetch())
    except Exception as e:
        events.append({"section": "ukmto", "title": f"⚠️ خطأ في UKMTO: {e}"})

    if include_ais:
        try:
            events.extend(mon_ais.fetch())
        except Exception as e:
            events.append({"section": "ais", "title": f"⚠️ خطأ في AIS: {e}"})

    return events


def main():
    title = "📄 تقرير الرصد والتحديث التشغيلي"
    events = collect_events(include_ais=True)

    # ✅ الآن run موجودة في report_official.py (بعد الاستبدال)
    report_official.run(
        title=title,
        events=events,
        only_if_new=False
    )


if __name__ == "__main__":
    main()
