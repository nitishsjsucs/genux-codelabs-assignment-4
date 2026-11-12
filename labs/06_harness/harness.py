"""A minimal coding-agent harness with UI tools - the loop that the other labs plug into.

    user text -> [model call -> tool calls -> tool results -> model call ...] -> final text
                 bounded by MAX_STEPS; every tool failure is a *result*, never an exception

A UI tool is an ordinary tool whose side effect is "show something on every
attached surface". Surfaces are pluggable: TerminalSurface prints (the
coding-agent case), WebSurface collects events that serve.py streams to a page
(the product case). Same loop, same tool calls, two renderings.

Validation errors are returned to the model as the tool result, so a model that
emits an invalid spec sees exactly what was wrong and can fix it on the next
step - the self-correction loop shown in mode 2.

User actions on a surface come back as `inject_action()`: a user turn the model
reads ("[ui-action] schedule_ev_charge {...}"), after the server has checked the
action against the allow-list.
"""

from __future__ import annotations

import json
import uuid
from typing import Callable, Dict, Iterator, List, Optional

from common import labkit, term
from common.llm import assistant_message

MAX_STEPS = 8


class Tool:
    def __init__(self, name: str, description: str, parameters: dict, fn: Callable[[dict, "Harness"], str]):
        self.name, self.description, self.parameters, self.fn = name, description, parameters, fn

    def schema(self) -> dict:
        return {"name": self.name, "description": self.description, "parameters": self.parameters}


class TerminalSurface:
    """Draws UI events as text (a coding agent in a terminal)."""

    def __init__(self, out: Callable[[str], None] = print):
        self.out = out

    def emit(self, event: dict) -> None:
        k = event["kind"]
        if k == "render":
            self.out("  ┌ surface: render " + "─" * 48)
            for line in term.to_text(event["tree"]).splitlines():
                self.out("  │ " + line)
            self.out("  └" + "─" * 66)
        elif k == "html":
            self.out(f"  ┌ surface: generated HTML - {event['title']} ({event['bytes']} bytes)")
            self.out(f"  │ terminals cannot run it; saved as {event['artifact']}")
            self.out("  └ open the web surface (python3 serve.py) to see it sandboxed")


class WebSurface:
    """Collects events for the page; serve.py streams them as SSE."""

    def __init__(self):
        self.events: List[dict] = []

    def emit(self, event: dict) -> None:
        self.events.append(event)


class Harness:
    def __init__(self, model, tools: List[Tool], system: str, surfaces: Optional[list] = None):
        self.model, self.system = model, system
        self.tools: Dict[str, Tool] = {t.name: t for t in tools}
        self.surfaces = surfaces if surfaces is not None else [TerminalSurface()]
        self.messages: List[dict] = []
        self.id = uuid.uuid4().hex[:8]
        self.state: dict = {}  # what the UI tools last showed, for follow-ups

    def show(self, event: dict) -> None:
        for s in self.surfaces:
            s.emit(event)

    def run(self, user_text: str) -> Iterator[dict]:
        """One user turn, as a stream of events (the same events every surface receives)."""
        self.messages.append({"role": "user", "content": user_text})
        schemas = [t.schema() for t in self.tools.values()]
        for step in range(1, MAX_STEPS + 1):
            text, calls = [], {}
            for piece in self.model.stream(self.messages, schemas, self.system):
                if piece[0] == "text":
                    text.append(piece[1])
                elif piece[0] == "tool_start":
                    calls[piece[1]] = {"id": piece[1], "name": piece[2], "arguments": ""}
                elif piece[0] == "tool_args":
                    calls[piece[1]]["arguments"] += piece[2]
            self.messages.append(assistant_message(self.model, "".join(text), list(calls.values())))
            if text:
                yield {"kind": "text", "step": step, "text": "".join(text)}
            if not calls:
                yield {"kind": "done", "steps": step}
                return
            for call in calls.values():
                yield {"kind": "tool_call", "step": step, "name": call["name"], "args": _short_args(call["arguments"])}
                before = self._mark()
                result, ok = self.execute(call)
                for e in self._since(before):
                    yield e
                yield {"kind": "tool_result", "step": step, "name": call["name"], "ok": ok, "content": result}
                self.messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
        yield {"kind": "error", "message": f"stopped after {MAX_STEPS} steps"}

    def inject_action(self, name: str, params: dict) -> Iterator[dict]:
        """A click on a surface becomes a user turn - after the allow-list check."""
        try:
            labkit.check_action(name, params)
        except (PermissionError, ValueError) as error:
            yield {"kind": "error", "message": f"action refused: {error}"}
            return
        yield {"kind": "action", "name": name, "params": params}
        yield from self.run(labkit.action_text(name, params))

    def execute(self, call: dict):
        tool = self.tools.get(call["name"])
        if tool is None:
            return f"error: unknown tool {call['name']}; tools: {sorted(self.tools)}", False
        try:
            args = json.loads(call["arguments"] or "{}")
        except json.JSONDecodeError as error:
            return f"error: arguments are not valid JSON ({error})", False
        try:
            result = tool.fn(args, self)
        except Exception as error:  # noqa: BLE001 - the model must see the failure, not the user
            return f"error: {error}", False
        return result, not result.startswith("error")

    # events emitted by tools during execute() are collected from the WebSurface-like buffer below
    def _mark(self) -> int:
        self._buffer = getattr(self, "_buffer", [])
        return len(self._buffer)

    def _since(self, mark: int) -> List[dict]:
        return self._buffer[mark:]

    def ui(self, event: dict) -> None:
        """Called by UI tools: show on every surface and record for the event stream."""
        self._buffer = getattr(self, "_buffer", [])
        self._buffer.append(event)
        self.show(event)


def _short_args(arguments: str, limit: int = 160) -> str:
    return arguments if len(arguments) <= limit else arguments[:limit - 3] + "..."


def print_events(events: Iterator[dict], out=print) -> List[dict]:
    seen = []
    for e in events:
        seen.append(e)
        k = e["kind"]
        if k == "text":
            out(f"step {e['step']} model: {e['text']}")
        elif k == "tool_call":
            out(f"step {e['step']} tool_call  {e['name']}({e['args'][:110]}{'...' if len(e['args']) > 110 else ''})")
        elif k == "tool_result":
            out(f"step {e['step']} tool_result {'ok ' if e['ok'] else 'ERR'} {e['content'][:300]}")
        elif k == "action":
            out(f"surface action -> {e['name']} {e['params']}")
        elif k == "done":
            out(f"done after {e['steps']} model calls")
        elif k == "error":
            out(f"ERROR {e['message']}")
    return seen
