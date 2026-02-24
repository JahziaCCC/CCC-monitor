# main.py
import os
import datetime

import report_official
import mon_firms
import mon_gdacs
import mon_ukmto
import mon_ais
import risk_food

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))


def _now_ksa():
    return datetime.datetime.now(tz=KSA_TZ)


def _safe_call(func, label: str, section: str):
    """
    يرجع [] إذا فشل المصدر، ويضيف حدث ملاحظة (ضمن نفس القسم) بدون كسر التشغيل.
    """
    try:
        out = func() or []
        # تأكد أنها قائمة dict
        if not isinstance(out, list):
            return [{
                "section": section,
                "title": f"ℹ️ ملاحظة: {label} رجّع نوع غير متوقع."
            }]
        return out
    except Exception as e:
        return [{
            "section": section,
            "title": f"ℹ️ ملاحظة: تعذر جلب بيانات {label} مؤقتاً. ({type(e).__name__})"
        }]


def collect_events_ccc(include_ais=True):
    events = []
    events += _safe_call(risk_food.get_events, "سلاسل الإمداد الغذائي", "food")
    events += _safe_call(mon_gdacs.get_events, "GDACS/الكوارث الطبيعية", "gdacs")
    events += _safe_call(mon_firms.get_events, "FIRMS/الحرائق", "fires")
    events += _safe_call(mon_ukmto.get_events, "UKMTO/التحذيرات البحرية", "ukmto")

    if include_ais:
        events += _safe_call(mon_ais.get_events, "AIS/حركة السفن", "ais")
    else:
        events.append({"section": "ais", "title": "ℹ️ AIS غير مفعّل (مستبعد من التقرير)."})

    return events


def run_ccc():
    include_ais = os.environ.get("INCLUDE_AIS", "1").strip() != "0"
    only_if_new = os.environ.get("ONLY_IF_NEW", "1").strip() != "0"

    now = _now_ksa()
    report_title = "📄 تقرير الرصد والتحديث التشغيلي"
    # رقم تقرير بسيط
    report_id = f"RPT-{now.strftime('%Y%m%d-%H%M%S')}"

    events = collect_events_ccc(include_ais=include_ais)

    # run() تقبل kwargs ولا تكسر
    report_official.run(
        report_title=report_title,
        report_id=report_id,
        events=events,
        include_ais=include_ais,
        only_if_new=only_if_new,
    )


if __name__ == "__main__":
    print("🚀 CCC Monitor Running...")
    run_ccc()
