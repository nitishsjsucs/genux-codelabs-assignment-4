"""Small helpers every lab uses: the action round-trip and script phases."""

from __future__ import annotations

import json
from typing import Optional, Tuple

from common import data

ACTION_PREFIX = "[ui-action]"


def action_text(name: str, params: dict) -> str:
    """How a UI action is phrased to the model: a user turn the model can read."""
    return f"{ACTION_PREFIX} {name} {json.dumps(params, sort_keys=True)}"


def parse_action(text: str) -> Optional[Tuple[str, dict]]:
    if not isinstance(text, str) or not text.startswith(ACTION_PREFIX):
        return None
    rest = text[len(ACTION_PREFIX):].strip()
    name, _, params = rest.partition(" ")
    return name, json.loads(params or "{}")


def check_action(name: str, params: dict) -> None:
    """The server-side gate. A click is a request, not a permission."""
    if name not in data.ALLOWED_ACTIONS:
        raise PermissionError(f"action {name!r} is not allowed; allowed: {sorted(data.ALLOWED_ACTIONS)}")
    if not isinstance(params, dict):
        raise ValueError("action params must be an object")
    if name == "schedule_ev_charge":
        windows = {w["window"] for w in data.CHARGE_WINDOWS}
        if params.get("window") not in windows:
            raise ValueError(f"unknown charge window {params.get('window')!r}; expected one of {sorted(windows)}")


def schedule(window: str) -> dict:
    """The (pretend) side effect: book the charge. Returns what the UI shows."""
    check_action("schedule_ev_charge", {"window": window})
    cost = next(w["cost"] for w in data.CHARGE_WINDOWS if w["window"] == window)
    return {"window": window, "cost": cost, "status": "scheduled",
            "message": f"Booked: the EV will charge {window} (estimated {data.money(cost)})."}


def last_user(messages: list) -> str:
    for m in reversed(messages):
        if m["role"] == "user":
            return m.get("content") or ""
    return ""


def turns_since_user(messages: list) -> int:
    """Assistant turns since the last user message - which step of a scripted reply we are on."""
    n = 0
    for m in reversed(messages):
        if m["role"] == "user":
            return n
        if m["role"] == "assistant":
            n += 1
    return n


def last_tool_result(messages: list) -> str:
    for m in reversed(messages):
        if m["role"] == "tool":
            return m.get("content") or ""
        if m["role"] == "user":
            return ""
    return ""
