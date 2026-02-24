# report_air.py
import sys
import report_official

import mon_dust  # <-- اسم ملفك الصحيح: mon_dust.py

def main():
    print("🌪️ Air Report Running...")

    # mon_dust.collect() لازم ترجع قائمة events
    # وكل event يكون فيه:
    # {"section":"other" أو "dust", "title":"..."}
    events = []
    if hasattr(mon_dust, "collect"):
        events = mon_dust.collect()
    else:
        raise RuntimeError("mon_dust.py missing function: collect()")

    # نرسل التقرير كـ "تقرير جودة الهواء" (منفصل)
    report_official.run(
        events,
        report_title="🌪️ تقرير الغبار وجودة الهواء (PM10)",
        include_ais=False
    )

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[FATAL] {e}")
        sys.exit(1)
