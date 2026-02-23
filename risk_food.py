# risk_food.py

def food_supply_summary(
    has_gdacs=False,
    gdacs_mentions_saudi=False,
    has_ukmto=False,
    ais_total=0,
    has_fires=False,
):
    lines = []

    if has_gdacs or has_ukmto or ais_total > 20 or has_fires:
        lines.append("• حدث إقليمي/تشغيلي قد يؤثر على تدفق سلاسل الإمداد.")
    else:
        lines.append("• لا توجد مؤشرات تشغيلية مؤثرة حالياً.")

    return lines
