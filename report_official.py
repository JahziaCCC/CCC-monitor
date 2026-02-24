# report_official.py
import os
import json
import hashlib
import datetime
import requests
import re
from typing import Dict, List, Any, Optional, Tuple

STATE_FILE = "mewa_state.json"
KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))

BOT = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# =========================
# Helpers
# =========================

def _now_ksa():
    return datetime.datetime.now(tz=KSA_TZ)

def _utcnow():
    return datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)

def _load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_state(state: dict):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def _tg_send(text: str):
    if not BOT or not CHAT_ID:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

    url = f"https://api.telegram.org/bot{BOT}/sendMessage"
    r = requests.post(
        url,
        json={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True},
        timeout=30
    )
    r.raise_for_status()

def _safe_int(x, default=None):
    try:
        return int(x)
    except Exception:
        return default

def _safe_float(x, default=None):
    try:
        return float(x)
    except Exception:
        return default

def _km_from_text(title: str) -> Optional[int]:
    # match "~581 كم" or "(~581 كم)" or "581 km"
    m = re.search(r"~\s*(\d+)\s*(?:كم|km)", title, re.IGNORECASE)
    if m:
        return _safe_int(m.group(1))
    m = re.search(r"(\d+)\s*(?:كم|km)", title, re.IGNORECASE)
    if m:
        return _safe_int(m.group(1))
    return None

def _has_ksa_hint(text: str) -> bool:
    t = (text or "").lower()
    hints = [
        "saudi", "saudi arabia", "ksa", "kingdom",
        "السعودية", "المملكة", "داخل السعودية", "داخل المملكة"
    ]
    return any(h in t for h in hints)

def _lines_from_titles(items, limit=12):
    out = []
    for e in (items or [])[:limit]:
        t = (e.get("title") or "").strip()
        if t:
            out.append(f"- {t}")
    return out if out else ["- لا يوجد"]

def _group_events(events):
    """
    Expected event format:
    {
      "section": "gdacs|fires|ukmto|ais|food|other",
      "title": "...",
      "severity": optional "red/orange/yellow/green" etc,
      "meta": optional dict
    }
    """
    grouped = {
        "food": [],
        "gdacs": [],
        "fires": [],
        "ukmto": [],
        "ais": [],
        "other": []
    }
    for e in events or []:
        sec = (e.get("section") or "other").lower()
        if sec not in grouped:
            sec = "other"
        grouped[sec].append(e)
    return grouped

# =========================
# Risk model (simple / stable)
# =========================

def _risk_score(grouped: Dict[str, List[dict]]) -> Tuple[int, str, str]:
    """
    Returns: (score 0-100, level_emoji_text, general_status_text)
    """
    score = 0

    # Fires: informational unless high FRP/count in titles
    fires = grouped.get("fires") or []
    if fires:
        # first line usually contains count/frp
        top_title = (fires[0].get("title") or "")
        # try parse "— 173 رصد" and "(أعلى FRP: 69.4)"
        cnt = None
        m = re.search(r"(\d+)\s*(?:رصد|رُصد)", top_title)
        if m:
            cnt = _safe_int(m.group(1))
        frp = None
        m2 = re.search(r"FRP[:\s]*([0-9]+(?:\.[0-9]+)?)", top_title, re.IGNORECASE)
        if m2:
            frp = _safe_float(m2.group(1))

        if cnt is not None and cnt >= 200:
            score += 35
        elif cnt is not None and cnt >= 100:
            score += 25
        elif cnt is not None and cnt >= 30:
            score += 15
        else:
            score += 10

        if frp is not None and frp >= 80:
            score += 25
        elif frp is not None and frp >= 60:
            score += 15

    # GDACS: higher if explicitly mentions KSA; else awareness
    gdacs = grouped.get("gdacs") or []
    if gdacs:
        t = (gdacs[0].get("title") or "")
        if _has_ksa_hint(t):
            score += 35
        else:
            score += 12

    # UKMTO / AIS: if any alerts
    ukmto = grouped.get("ukmto") or []
    if ukmto and _lines_from_titles(ukmto) != ["- لا يوجد"]:
        score += 25

    ais = grouped.get("ais") or []
    if ais and _lines_from_titles(ais) != ["- لا يوجد"]:
        score += 10

    # Food: any operational note increases moderate
    food = grouped.get("food") or []
    if food and _lines_from_titles(food) != ["- لا يوجد"]:
        score += 10

    # Clamp
    if score < 0:
        score = 0
    if score > 100:
        score = 100

    # Level mapping
    if score >= 80:
        level = "🔴 حرج"
        status = "حرجة"
    elif score >= 60:
        level = "🟠 مرتفع"
        status = "نشاط مرتفع"
    elif score >= 40:
        level = "🟡 مراقبة"
        status = "مراقبة"
    else:
        level = "🟢 منخفض"
        status = "مراقبة"

    return score, level, status

# =========================
# Executive "Top event" selection
# =========================

def _pick_top_event_text(grouped: Dict[str, List[dict]]) -> Tuple[str, List[str]]:
    """
    Rule (A):
    - If GDACS mentions Saudi -> pick GDACS headline
    - Else pick Fires headline if exists (inside KSA) (because dust removed)
    - Else nothing
    Also return operational explanation lines for the executive summary.
    """
    explain = []

    gdacs = grouped.get("gdacs") or []
    if gdacs:
        gd_t = (gdacs[0].get("title") or "").strip()
        if gd_t and _has_ksa_hint(gd_t):
            explain.append("• العامل الرئيسي: حدث GDACS يذكر المملكة بشكل مباشر (تأثير أعلى).")
            return gd_t, explain

    fires = grouped.get("fires") or []
    if fires:
        f_t = (fires[0].get("title") or "").strip()
        if f_t:
            explain.append("• العامل الرئيسي: مؤشرات حرائق/نقاط رصد نشطة داخل المملكة (للاطلاع).")
            if gdacs:
                explain.append("• GDACS: حدث إقليمي للتوعية — لا يوجد ذكر مباشر للمملكة (تأثير
