import json, os, time

STATE_FILE = "state.json"

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def seen(state, key: str) -> bool:
    return key in state.get("seen", {})

def mark_seen(state, key: str):
    state.setdefault("seen", {})
    state["seen"][key] = int(time.time())

def prune_seen(state, days=30):
    cutoff = int(time.time()) - days * 86400
    state.setdefault("seen", {})
    state["seen"] = {k: v for k, v in state["seen"].items() if v >= cutoff}
