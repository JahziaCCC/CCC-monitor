# main.py
import os

import report_official
import mon_fires
import mon_gdacs
import mon_ais

# Dust Report (منفصل - اختياري)
try:
    import mon_dusty
    HAS_DUST = True
except Exception:
    HAS_DUST = False

# UKMTO (اختياري)
try:
    import mon_ukmto
    HAS_UKMTO = True
except Exception:
    HAS_UKMTO = False


def _safe_call(fn, label: str, section_fallback="other"):
    """
    يمنع توقف الـ run: أي خطأ يرجّع Event واحد بملاحظة، ويكمل التقرير.
    """
    try:
        return fn() or []
    except Exception as e:
        return [{
            "section": section_fallback,
            "title": f"ℹ️ ملاحظة: تعذر جلب بيانات {label} مؤقتاً. ({type(e).__name__})"
        }]


def collect_events_ccc():
    events = []
    events += _safe_call(mon_fires.get_events, "FIRMS/حرائق الغابات", "fires")
    events += _safe_call(mon_gdacs.get_events, "GDACS/الكوارث الطبيعية", "gdacs")
    events += _safe_call(mon_ais.get_events, "AIS/السفن والموانئ", "ais")

    if HAS_UKMTO:
        events += _safe_call(mon_ukmto.get_events, "UKMTO/تحذيرات بحرية", "ukmto")

    # Food (اختياري)
    try:
        import risk_food
        events += _safe_call(risk_food.get_events, "سلاسل الإمداد الغذائي", "food")
    except Exception:
        pass

    return events


def run_ccc():
    events = collect_events_ccc()
    report_official.run(
        events=events,
        report_title="📄 تقرير الرصد والتحديث التشغيلي",
        only_if_new=True
    )


def run_dust():
    if not HAS_DUST:
        raise RuntimeError("mon_dusty.py not found")
    mon_dusty.run(only_if_new=True)


if __name__ == "__main__":
    job = (os.environ.get("JOB") or "ccc").strip().lower()
    if job == "dust":
        run_dust()
    else:
        run_ccc()
