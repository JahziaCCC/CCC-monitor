# main.py
import os

import report_official
import mon_fires
import mon_gdacs
import mon_ais  # إذا اسمك mon_ais_ports.py غيّرها هنا أو أعد تسمية الملف
import mon_dusty

# إذا عندك UKMTO:
try:
    import mon_ukmto
    HAS_UKMTO = True
except Exception:
    HAS_UKMTO = False


def _safe_call(fn, section_name: str):
    """
    يمنع توقف الـ run: أي خطأ من المصدر يرجع حدث واحد فيه رسالة توضيحية.
    """
    try:
        return fn() or []
    except Exception as e:
        return [{
            "section": "other",
            "title": f"ℹ️ ملاحظة: تعذر جلب بيانات {section_name} مؤقتاً. ({type(e).__name__})"
        }]


def collect_events_ccc():
    events = []
    events += _safe_call(mon_fires.get_events, "FIRMS/الحرائق")
    events += _safe_call(mon_gdacs.get_events, "GDACS/الكوارث الطبيعية")
    events += _safe_call(mon_ais.get_events, "AIS/السفن والموانئ")

    if HAS_UKMTO:
        events += _safe_call(mon_ukmto.get_events, "UKMTO/تحذيرات بحرية")

    # Food (إذا عندك ملف risk_food.py مثلاً)
    try:
        import risk_food
        events += _safe_call(risk_food.get_events, "سلاسل الإمداد الغذائي")
    except Exception:
        pass

    return events


def run_ccc():
    events = collect_events_ccc()
    report_official.run(
        events=events,
        report_title="📄 تقرير الرصد والتحديث التشغيلي",
        only_if_new=True,       # مهم: يمنع التكرار
        include_ais=True
    )


def run_dust():
    # mon_dusty يرسل تقريره بنفسه عبر تيليجرام
    mon_dusty.run(only_if_new=True)


if __name__ == "__main__":
    # اختيار الوظيفة من ENV (GitHub Actions)
    job = (os.environ.get("JOB") or "ccc").lower().strip()
    if job == "dust":
        run_dust()
    else:
        run_ccc()
