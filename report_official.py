def run(
    report_title="📄 تقرير الرصد والتحديث التشغيلي",
    report_id=None,
    only_if_new=False,
    include_ais=True,
    events=None,
):
    """
    Main report runner
    """

    # حماية لو ما وصل events
    if events is None:
        events = []

    # بناء التقرير
    grouped = _group_events(events)

    report_text = _build_report_text(
        report_title,
        grouped,
        include_ais
    )

    # طباعة التقرير
    print(report_text)

    return report_text
