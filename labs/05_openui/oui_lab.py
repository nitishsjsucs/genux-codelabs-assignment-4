"""What the four OpenUI Lang modes share: templates, the streaming relay, the action round trip."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterator, List

import openui
from common import catalog, data, fixtures, labkit, sandbox, term

HERE = Path(__file__).resolve().parent
S = data.summary()
NAMES = {"Solar generated": "solar", "Self-sufficiency": "selfsuff", "Grid import cost": "cost", "Home battery": "battery",
         "Solar vs usage": "chart_card", "Solar generated per day": "chart", "When to charge the EV": "ev_card",
         "Today on the clock": "clock_card", "Energy clock": "clock", "Your solar week": "title"}


def signature_lines(open_ended: bool) -> str:
    sigs = {k: v for k, v in openui.SIGNATURES.items() if open_ended or k != "HtmlArtifact"}
    return "\n".join(f"{k}({', '.join(v)})" for k, v in sigs.items())


def system_prompt(open_ended: bool, extra: str = "") -> str:
    return ("You are VoltPilot. Reply ONLY with an OpenUI Lang program: one statement per line, `name = Expr`. "
            "Write `root = ...` first and refer to names defined later. Components take positional arguments:\n"
            + signature_lines(open_ended) + "\nStack direction is \"row\" or \"column\"; gap is \"s\", \"m\" or \"l\". "
            "Strings use double quotes with backslash escapes; keep every statement on one line. " + extra
            + "\nDATA: " + json.dumps({"summary": S, "week": data.WEEK, "windows": data.CHARGE_WINDOWS}))


# ---------------------------------------------------------------- 1. static: developer templates with typed slots

SLOT = re.compile(r"\{\{(\w+)\}\}")
TEMPLATES = {p.stem: p.read_text() for p in sorted((HERE / "templates").glob("*.oui"))}


def slots(template: str) -> List[str]:
    return sorted(set(SLOT.findall(TEMPLATES[template])))


def fill(template: str, values: dict) -> str:
    """The app fills the developer's template. Each value becomes an OpenUI *literal* (json-encoded), so a
    value can never inject a component call or a reference - the model supplies data, not structure."""
    if template not in TEMPLATES:
        raise ValueError(f"unknown template {template!r}; templates: {sorted(TEMPLATES)}")
    missing = [s for s in slots(template) if s not in values]
    if missing:
        raise ValueError(f"missing slots for {template}: {missing}")
    for k, v in values.items():
        if not isinstance(v, (str, int, float, list)) or isinstance(v, bool):
            raise ValueError(f"slot {k}: only strings, numbers and lists are allowed")
    return SLOT.sub(lambda m: openui.lit(values[m.group(1)]), TEMPLATES[template])


# ---------------------------------------------------------------- streaming

def relay(pieces: Iterator[tuple], program: openui.Program, source: str = "model") -> Iterator[dict]:
    """Forward the model's text as chunks; check HtmlArtifact documents as their statements complete."""
    for piece in pieces:
        if piece[0] != "text":
            continue
        for name in program.feed(piece[1]):
            problem = _artifact_problem(program, name)
            if problem:
                del program.statements[name]
                yield {"from": "app", "error": f"{name}: HtmlArtifact refused - {problem}", "drop": name}
        yield {"from": source, "chunk": piece[1]}
    for name in program.close():
        problem = _artifact_problem(program, name)
        if problem:
            del program.statements[name]
            yield {"from": "app", "error": f"{name}: HtmlArtifact refused - {problem}", "drop": name}


def _artifact_problem(program: openui.Program, name: str) -> str:
    e = program.statements.get(name)
    if e and e[0] == "call" and e[1] == "HtmlArtifact" and len(e[2]) >= 2 and e[2][1][0] == "lit":
        return ", ".join(sandbox.policy_check(str(e[2][1][1])))
    return ""


def finish(program: openui.Program, allow_generated: bool) -> dict:
    tree = program.tree()
    errors = program.errors + [f"undefined: {n}" for n in program.pending()] + catalog.validate_tree(tree, allow_generated)
    return {"from": "app", "done": True, "statements": len(program.statements), "errors": errors}


def print_stream(frames: List[dict], allow_generated: bool) -> openui.Program:
    """Replay the chunks the way the page does, printing each completed statement and the pending refs."""
    program = openui.Program()
    refused = set()
    for f in frames:
        if "template" in f:
            print(f"  [app  ] template {f['template']!r} filled with slots {f['slots']}")
        if "error" in f:
            print(f"  [{f['from']:<5}] REFUSED {f['error']}")
            if f.get("drop"):
                refused.add(f["drop"])
        if "chunk" in f:
            for name in program.feed(f["chunk"]):
                if name in refused:  # the page drops a statement the server refused
                    del program.statements[name]
                    continue
                _show(program, name)
    for name in program.close():
        _show(program, name)
    done = next((f for f in frames if f.get("done")), None)
    if done:
        print(f"\n{done['statements']} statements, errors: {done['errors'] or 'none'}")
    print(term.to_text(program.tree()))
    return program


def _show(program: openui.Program, name: str) -> None:
    pend = program.pending()
    e = program.statements[name]
    head = e[1] if e[0] == "call" else e[0]
    print(f"  line {program.lines:>2}: {name:<11} = {head:<12} pending refs: {len(pend):>2} {('(' + ', '.join(pend[:5]) + (', ...' if len(pend) > 5 else '') + ')') if pend else ''}")


# ---------------------------------------------------------------- actions

def action_program(name: str, params: dict, root_line: str) -> str:
    text = "Okay - nothing booked." if name == "dismiss" else labkit.schedule(params.get("window"))["message"]
    return f"booked = Text({openui.lit(text)}, \"success\")\n{root_line}\n"


def root_with_booked(program_text: str) -> str:
    """Re-declare root with `booked` as its second child (a later statement replaces an earlier one)."""
    first = program_text.splitlines()[0]
    return re.sub(r"\[(\w+), ", r"[\1, booked, ", first, count=1)


def reply_text(frames) -> str:
    return "".join(f.get("chunk", "") for f in frames)


def handle_action(body: dict, model, system: str) -> Iterator[dict]:
    name, params = body.get("action"), body.get("params") or {}
    try:
        labkit.check_action(name, params)
    except (PermissionError, ValueError) as error:
        yield {"from": "app", "error": f"action refused: {error}"}
        return
    turns = [{"role": "user", "content": data.PROMPT}, {"role": "user", "content": labkit.action_text(name, params)}]
    yield from relay(model.stream(turns, system=system), openui.Program())


def program_for(with_actions: bool = False, with_generated: bool = False) -> str:
    return openui.from_tree(fixtures.dashboard_tree(with_actions, with_generated), NAMES)
