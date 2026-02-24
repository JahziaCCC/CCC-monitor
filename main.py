# main.py
import report_official

import mon_firms
import mon_gdacs
import mon_ukmto
import mon_ais

def _safe_call(fn, label, section):
    try:
        return fn() or []
    except Exception as e:
        return [{
            "section": section,
            "title": f"ℹ️ ملاحظة: تعذر جلب بيانات {label} مؤقتاً. ({type(e).__name__})"
        }]

def collect_events_ccc():
    events = []
    # الكوارث الطبيعية
    events += _safe_call(mon_gdacs.get_events, "GDACS/الكوارث الطبيعية", "gdacs")
    # الحرائق
    events += _safe_call(mon_firms.get_events, "FIRMS/الحرائق", "fires")
    # UKMTO
    events += _safe_call(mon_ukmto.get_events, "UKMTO/تحذيرات بحرية", "ukmto")
    # AIS (اختياري: إذا تبغى تعطله احذف السطر هذا)
    events += _safe_call(mon_ais.get_events, "AIS/حركة السفن", "ais")
    return events

def main():
    print("🚀 CCC Monitor Running...")
    events = collect_events_ccc()
    report_official.run(events)

if __name__ == "__main__":
    main()
