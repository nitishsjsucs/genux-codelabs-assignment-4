"""What the four json-render modes share: the system prompt, the patch relay, the action round trip."""

from __future__ import annotations

import json
from typing import Iterator, List, Optional

import jsonrender as jr
from common import catalog, data, fixtures, labkit, sandbox, term

S = data.summary()
METRIC_KEYS = {"Solar generated": "solar", "Self-sufficiency": "selfSufficiency", "Grid import cost": "importCost", "Home battery": "battery"}


def system_prompt(allow_custom: bool, extra: str = "") -> str:
    comps = catalog.describe_for_prompt(allow_generated=False)
    if allow_custom:
        comps += "\n- CustomHtml { title: str, html: str, height?: num } - a self-contained HTML document, run in a sandbox"
    return (
        "You are VoltPilot's dashboard builder. Output JSONL: one RFC 6902 JSON Patch operation per line that builds "
        "{root, elements, state}. Start with /root, then /elements/<id> parents first, and put each /state patch right "
        "after the first element that reads it. Props may be {\"$state\": \"/path\"} or {\"$template\": \"... ${/path} ...\"}. "
        "Buttons bind actions with an `on` field: {\"press\": {\"action\": name, \"params\": {...}}} (actions: "
        "schedule_ev_charge, dismiss).\nAVAILABLE COMPONENTS:\n" + comps + "\n" + extra
        + "\nDATA: " + json.dumps({"summary": S, "week": data.WEEK, "windows": data.CHARGE_WINDOWS})
    )


def relay(pieces: Iterator[tuple], stream: jr.SpecStream, source: str = "model") -> Iterator[dict]:
    """Model JSONL -> checked patches -> frames for the page."""
    for op in jr.patch_lines(pieces):
        if "error" in op:
            yield {"from": source, "error": op["error"]}
            continue
        if op.get("path") == "/state/clock/html" or op.get("path") == "/state/clock":
            html = op["value"] if isinstance(op.get("value"), str) else (op.get("value") or {}).get("html", "")
            problems = sandbox.policy_check(html)
            if problems:
                yield {"from": source, "error": "CustomHtml document refused: " + ", ".join(problems)}
                continue
        problem = stream.push(op)
        yield {"from": source, "error": problem} if problem else {"from": source, "patch": op}


def action_patches(name: str, params: dict) -> List[dict]:
    text = "Okay - nothing booked." if name == "dismiss" else labkit.schedule(params.get("window"))["message"]
    return [
        {"op": "add", "path": "/state/ev", "value": {"status": text}},
        {"op": "add", "path": "/elements/booked", "value": {"type": "Text", "props": {"text": {"$state": "/ev/status"}, "variant": "success"}, "children": []}},
        {"op": "add", "path": "/elements/main/children/1", "value": "booked"},
    ]


def handle_action(body: dict, model, system: str, spec: dict) -> Iterator[dict]:
    name, params = body.get("action"), body.get("params") or {}
    try:
        labkit.check_action(name, params)
    except (PermissionError, ValueError) as error:
        yield {"from": "app", "error": f"action refused: {error}"}
        return
    turns = [{"role": "user", "content": data.PROMPT}, {"role": "user", "content": labkit.action_text(name, params)}]
    yield from relay(model.stream(turns, system=system), jr.SpecStream(spec))


def action_script(base_spec: dict):
    def script(messages: list) -> dict:
        action = labkit.parse_action(labkit.last_user(messages))
        if action:
            return {"text": jr.to_jsonl(action_patches(*action))}
        return {"text": jr.to_jsonl(jr.spec_to_patches(base_spec))}
    return script


def dashboard_spec(with_actions: bool = False, with_generated: bool = False) -> dict:
    return jr.from_tree(fixtures.dashboard_tree(with_actions, with_generated), bind=METRIC_KEYS)


def print_frames(frames: List[dict], limit: Optional[int] = None) -> None:
    shown = frames if limit is None else frames[:limit]
    for f in shown:
        print(f"  [{f['from']:<5}] " + (jr.describe(f["patch"]) if "patch" in f else f"REFUSED {f['error']}" if "error" in f else "spec (app-shipped, %d elements)" % len(f["spec"]["elements"])))
    if limit is not None and len(frames) > limit:
        print(f"  ... {len(frames) - limit} more")


def print_render(spec: dict, allow_custom: bool) -> None:
    tree = jr.to_canonical(spec)
    print(f"\nvalidation: {jr.validate(spec, allow_custom) or 'ok'}")
    print("terminal renderer (same spec the page draws):\n" + term.to_text(tree))
