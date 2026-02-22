from datetime import datetime, timezone
from telegram import send
from state import load_state, save_state, prune_seen, seen, mark_seen

import mon_gdacs, mon_dust, mon_ukmto
# AIS فقط للتقرير (اختياري)
try:
    import mon_ais_ports
    HAS_AIS = True
except Exception:
    HAS_AIS = False

from report_official import build_official_report

def collect_events(include_ais: bool):
    events = []
    events.extend(mon_gdacs.fetch())
    events.extend(mon_dust.fetch())
    events.extend(mon_ukmto.fetch())
    if include_ais and HAS_AIS:
        events.extend(mon_ais_ports.fetch(sample_seconds=60))
    return events

def _report_no(state):
    # RPT-YYYYMMDD-### (عدّاد يومي)
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    key = f"rpt_seq_{today}"
    state[key] = int(state.get(key, 0)) + 1
    return f"RPT-{today}-{state[key]:03d}"

def run(label: str, only_if_new: bool, include_ais: bool):
    state = load_state()
    prune_seen(state, days=30)

    events = collect_events(include_ais=include_ais)

    new_count = 0
    for e in events:
        k = e.get("key")
        if not k:
            continue
        if not seen(state, k):
            mark_seen(state, k)
            new_count += 1

    if only_if_new and new_count == 0:
        save_state(state)
        return

    rpt_no = _report_no(state)
    msg = build_official_report(events, state, rpt_no)
    save_state(state)
    send(msg)

def main():
    # التقرير المجدول (دائم)
    run("📌 تقرير مُجدول", only_if_new=False, include_ais=True)

if __name__ == "__main__":
    main()
