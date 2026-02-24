def _gdacs_points_for_event(e: dict) -> int:
    """
    Risk Engine v2:
    - نقاط أساسية حسب اللون
    - مضاعف/إضافة حسب نوع الحدث
    """
    severity = (e.get("severity") or "Green").strip()

    base = {
        "Green": 2,
        "Yellow": 5,
        "Orange": 8,
        "Red": 15,
    }.get(severity, 2)

    event_type = (e.get("event_type") or "other").strip()

    type_bonus = {
        "earthquake": 2,
        "flood": 4,
        "drought": 4,
        "cyclone": 5,
        "volcano": 6,
        "landslide": 4,
        "wildfire": 3,
        "other": 1,
    }.get(event_type, 1)

    return base + type_bonus


def _compute_risk_index(grouped: dict) -> int:
    """
    يجمع نقاط الأقسام (GDACS + FIRMS + ..)
    """
    score = 0

    # GDACS
    for e in grouped.get("gdacs", []):
        t = (e.get("title") or "")
        if "لا يوجد" in t:
            continue
        score += _gdacs_points_for_event(e)

    # FIRMS (مثال: خفيف لأنه عندك منطق حرائق أصلاً)
    fires = grouped.get("fires", [])
    if fires and not any("لا يوجد" in (x.get("title") or "") for x in fires):
        score += 6  # أو اربطه بمنطقك الحالي

    # UKMTO
    uk = grouped.get("ukmto", [])
    if uk and not any("لا يوجد" in (x.get("title") or "") for x in uk):
        score += 8

    # AIS
    ais = grouped.get("ais", [])
    if ais and not any("لا يوجد" in (x.get("title") or "") for x in ais):
        score += 4

    # سقف 100
    if score > 100:
        score = 100

    return int(score)


def _risk_level(score: int) -> str:
    if score >= 80:
        return "🔴 حرج"
    if score >= 60:
        return "🟠 مرتفع"
    if score >= 30:
        return "🟡 مراقبة"
    return "🟢 منخفض"
