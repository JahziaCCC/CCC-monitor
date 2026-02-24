# main.py
import importlib
import datetime

import report_official  # ملف التقرير الرئيسي

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))


def _safe_import(name: str):
    """يحاول يستورد موديل، إذا ما لقى يرجع None بدل ما يوقف التشغيل."""
    try:
        return importlib.import_module(name)
    except Exception:
        return None


def _extend_events(events: list, module, module_name: str):
    """ينادي module.fetch() إذا موجود ويرجع Events ويضيفها للقائمة."""
    if module is None:
        return
    fetch = getattr(module, "fetch", None)
    if not callable(fetch):
        return
    try:
        data = fetch()
        if isinstance(data, list):
            events.extend(data)
    except Exception as e:
        # نسجل الخطأ كـ event بدال ما ينهار التشغيل
        events.append({
            "section": "other",
            "title": f"⚠️ خطأ في {module_name}: {e}",
            "meta": {"module": module_name}
        })


def collect_events(include_ais: bool = True):
    """
    يجمع كل الأحداث للتقرير الرئيسي CCC Monitor.
    ⚠️ الغبار/PM10 تم إلغاءه بالكامل من هنا (صار له تقرير منفصل report_air.py).
    """
    events = []

    # ===== مصادر الأحداث (عدّل الأسماء إذا مختلفة عندك) =====
    mon_gdacs = _safe_import("mon_gdacs")
    mon_fires = _safe_import("mon_fires")      # FIRMS
    mon_ukmto = _safe_import("mon_ukmto")      # UKMTO (قد يعطي 403 إذا ممنوع)
    risk_food = _safe_import("risk_food")      # سلاسل الإمداد

    # AIS عندك كان اسم الملف mon_ais_ports.py ثم غيرته إلى mon_ais.py
    mon_ais = _safe_import("mon_ais") or _safe_import("mon_ais_ports")

    # ===== جمع الأحداث =====
    _extend_events(events, risk_food, "risk_food")
    _extend_events(events, mon_gdacs, "mon_gdacs")
    _extend_events(events, mon_fires, "mon_fires")
    _extend_events(events, mon_ukmto, "mon_ukmto")

    if include_ais:
        _extend_events(events, mon_ais, "mon_ais / mon_ais_ports")

    # ===== مهم جداً: الغبار تم إلغاءه =====
    # لا يوجد: events.extend(mon_dust.fetch())

    return events


def run_report(report_title: str, only_if_new: bool, include_ais: bool):
    """
    يشغّل report_official بطريقة متوافقة مع أكثر من نسخة.
    """
    events = collect_events(include_ais=include_ais)

    # 1) إذا عندك report_official.run(...) (مثل اللي كان عندك سابقاً)
    if hasattr(report_official, "run") and callable(getattr(report_official, "run")):
        # ملاحظة: بعض النسخ تتوقع أن report_official.run تجمع بنفسها،
        # لكن عندك واضح إنها تعتمد على events داخلها.
        # إذا نسختك تتوقع signature مختلف، قلّي وأنا أضبطه فوراً.
        return report_official.run(report_title, only_if_new=only_if_new, include_ais=include_ais, events=events)

    # 2) إذا عندك report_official.main(...) وتستقبل events
    if hasattr(report_official, "main") and callable(getattr(report_official, "main")):
        try:
            return report_official.main(events=events, report_title=report_title, only_if_new=only_if_new)
        except TypeError:
            # إذا main() ما تقبل بارامترات، شغّلها بدون
            return report_official.main()

    # 3) إذا عندك build_report_text + _tg_send (أحياناً تكون داخل الملف)
    if hasattr(report_official, "build_report_text") and callable(getattr(report_official, "build_report_text")):
        text = report_official.build_report_text(events)
        # إرسال
        if hasattr(report_official, "_tg_send") and callable(getattr(report_official, "_tg_send")):
            return report_official._tg_send(text)
        raise RuntimeError("report_official.build_report_text موجود لكن لا يوجد _tg_send للإرسال")

    raise RuntimeError("لم أجد run() أو main() أو build_report_text داخل report_official.py")


def main():
    # هذا هو تشغيل CCC Monitor (التقرير الرئيسي)
    # غير العنوان إذا تبغى
    run_report(
        report_title="📌 تقرير مجدول",
        only_if_new=False,
        include_ais=True
    )


if __name__ == "__main__":
    main()
