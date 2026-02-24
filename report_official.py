import re

def _fires_stats(grouped):
    """
    يرجع (count, max_frp) لو موجودين، وإلا (0, 0)
    يعتمد على السطر الأول اللي يبدأ بـ 🔥
    """
    fires = grouped.get("fires") or []
    for e in fires:
        t = (e.get("title") or "").strip()
        if t.startswith("🔥"):
            m = re.search(r"—\s*(\d+)\s*رصد", t)
            m2 = re.search(r"أعلى\s*FRP:\s*([0-9.]+)", t)
            count = int(m.group(1)) if m else 0
            max_frp = float(m2.group(1)) if m2 else 0.0
            return count, max_frp
    return 0, 0.0
