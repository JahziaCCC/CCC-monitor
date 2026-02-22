from datetime import datetime, timezone
from telegram import send
from state import load_state, save_state, prune_seen, seen, mark_seen

import mon_gdacs, mon_dust, mon_ukmto

try:
    import mon_ais_ports
    HAS_AIS = True
except Exception:
    HAS_AIS = False

from report_official import build_official_report

# ===== إعدادات تنبيه ازدحام الموانئ =====
PORT_ALERT_ABS = 25   # تنبيه إذا وصل العدد لهذا الرقم أو أكثر
PORT_ALERT_JUMP = 10  # تنبيه إذا زاد فجأة بهذا المقدار أو أكثر
AIS_SAMPLE_SECONDS = 120  # مدة جمع AIS للتقرير
# =======================================

def collect_events(include_ais: bool):
    events = []
    events.extend(mon_gdacs.fetch())
    events.extend(mon_dust.fetch())
    events.extend(mon_ukmto.fetch())

    if include_ais and HAS_AIS:
        try:
            events.extend(mon_ais_ports.fetch(sample_seconds=AIS_SAMPLE_SECONDS))
        except Exception:
            pass

    return events

def _report_no(state):
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    key = f"rpt_seq_{today}"
    state[key] = int(state.get(key, 0)) + 1
    return f"RPT-{today}-{state[key]:03d}"

def _ports_congestion_alert(events, state):
    """
    يرجع رسالة تنبيه إذا كان هناك ازدحام/قفزة في أحد الموانئ.
    يعتمد على عناصر section=ports وبداخل meta.port + meta.count.
    """
    ports_state = state.setdefault("ports_last_counts", {})
    alerts = []

    for e in events:
        if e.get("section") != "ports":
            continue

        meta = e.get("meta") or {}
        port_name = meta.get("port") or "ميناء"
        current = int(meta.get("count", 0))

        prev = int(ports_state.get(port_name, 0))
        jump = current - prev

        # تحديث آخر قراءة
        ports_state[port_name] = current

        # شروط التنبيه
        if current >= PORT_ALERT_ABS:
            alerts.append(f"🚢 ازدحام مرتفع: {port_name}\n• العدد الحالي: {current} سفينة")
        elif jump >= PORT_ALERT_JUMP:
            alerts.append(
                f"📈 قفزة في الازدحام: {port_name}\n"
                f"• السابق: {prev} سفينة\n"
                f"• الحالي: {current} سفينة\n"
                f"• الزيادة: +{jump}"
            )

    if not alerts:
        return None

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    msg = (
        "🚨 تنبيه تشغيلي – ازدحام الموانئ (AIS)\n"
        f"🕒 {now}\n\n"
        + "\n\n".join(alerts)
    )
    return msg

def run(label: str, only_if_new: bool, include_ais: bool):
    state = load_state()
    prune_seen(state, days=30)

    events = collect_events(include_ais=include_ais)

    # حساب الجديد لمنع السبام في alerts workflow
    new_count = 0
    for e in events:
        k = e.get("key")
        if not k:
            continue
        if not seen(state, k):
            mark_seen(state, k)
            new_count += 1

    # تنبيه ازدحام الموانئ (إذا include_ais)
    ports_alert_msg = None
    if include_ais:
        ports_alert_msg = _ports_congestion_alert(events, state)

    # إذا كان هذا تشغيل تنبيهات فقط: لا ترسل شيء إذا لا جديد ولا تنبيه ازدحام
    if only_if_new and new_count == 0 and not ports_alert_msg:
        save_state(state)
        return

    # إرسال التنبيه أولاً (إن وجد)
    if ports_alert_msg:
        send(ports_alert_msg)

    # إرسال التقرير الرسمي
    rpt_no = _report_no(state)
    msg = build_official_report(events, state, rpt_no)

    save_state(state)
    send(msg)

def main():
    # التقرير المجدول (دائم) — يشمل AIS
    run("📌 تقرير مُجدول", only_if_new=False, include_ais=True)

if __name__ == "__main__":
    main()
