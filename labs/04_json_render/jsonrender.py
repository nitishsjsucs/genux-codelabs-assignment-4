"""json-render, re-implemented small: a catalog-bound element map, streamed as JSON Patch.

A json-render spec is a flat element map plus a state model:

    {"root": "main",
     "elements": {"main": {"type": "Card", "props": {"title": "..."}, "children": ["m1"]},
                  "m1":   {"type": "Metric", "props": {"label": "Solar", "value": {"$state": "/solar"}}},
                  "go":   {"type": "Button", "props": {"label": "Book"},
                           "on": {"press": {"action": "schedule_ev_charge", "params": {"window": {"$state": "/best"}}}}}},
     "state": {"solar": "133.3 kWh", "best": "10:30-15:00"}}

The model does not write the spec in one piece: it streams RFC 6902 patches,
one per line - /root first, then /elements/<id> and /state/... - so the page
can draw each element as soon as its line arrives (the flat map is why this
works: a nested tree is not valid JSON until its last bracket).

Prop expressions resolved against state: {"$state": "/path"} and
{"$template": "Solar: ${/solar}"}. Events: an element's `on` field maps an
event ("press") to an action binding {action, params}.

The catalog is the contract: it generates the prompt, validates the spec, and
maps types to renderers - here the web renderer (common/web/catalog.js) and a
terminal renderer (common/term.py): one spec, two targets.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Dict, Iterator, List, Optional

from common import catalog
from common.jsonpatch import PatchError, apply_op, escape, resolve
from common.sse import short

# json-render's catalog for this repo: the shared VoltPilot components, named as json-render users would.
TYPES = {"Card", "Row", "Column", "Text", "Metric", "BarChart", "Table", "Button"}
OPEN_TYPES = TYPES | {"CustomHtml"}


def resolve_value(value, state: dict):
    if isinstance(value, dict):
        if set(value) == {"$state"}:
            return resolve(state, value["$state"])
        if set(value) == {"$template"}:
            return re.sub(r"\$\{(/[^}]*)\}", lambda m: str(resolve(state, m.group(1), "")), value["$template"])
        return {k: resolve_value(v, state) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_value(v, state) for v in value]
    return value


def to_canonical(spec: dict) -> dict:
    """Spec -> canonical tree: expressions resolved, `on.press` -> Button action, CustomHtml -> GeneratedView."""
    state = spec.get("state") or {}
    elements = spec.get("elements") or {}

    def build(eid: str) -> dict:
        el = elements.get(eid)
        if el is None:
            return {"type": "__pending", "props": {"ref": eid}, "children": []}
        props = resolve_value(el.get("props") or {}, state)
        kind = el.get("type")
        if kind == "Button":
            press = (el.get("on") or {}).get("press") or {}
            props = {**props, "action": press.get("action", ""), "params": resolve_value(press.get("params") or {}, state)}
        if kind == "CustomHtml":
            kind, props = "GeneratedView", {"title": props.get("title", "Custom view"), "html": props.get("html") or "",
                                            "height": props.get("height", 260)}
        visible = el.get("visible")
        if isinstance(visible, dict) and "$state" in visible and not resolve(state, visible["$state"]):
            return {"type": "Column", "props": {}, "children": [], "id": eid}
        kids = [build(c) for c in el.get("children") or [] if c in elements]
        return {"type": kind, "props": {k: v for k, v in props.items() if v is not None}, "children": kids, "id": eid}

    root = spec.get("root")
    return build(root) if root in elements else {"type": "Column", "props": {}, "children": []}


def validate(spec: dict, allow_custom: bool = False) -> List[str]:
    allowed = OPEN_TYPES if allow_custom else TYPES
    errors = [f"/elements/{eid}: type {el.get('type')!r} is not in the catalog ({', '.join(sorted(allowed))})"
              for eid, el in (spec.get("elements") or {}).items() if el.get("type") not in allowed]
    if errors:
        return errors
    return catalog.validate_tree(to_canonical(spec), allow_generated=allow_custom)


class SpecStream:
    """Applies streamed patch lines to a growing spec - the Python twin of spec-stream.js."""

    def __init__(self, spec: Optional[dict] = None, writable: Optional[List[str]] = None):
        self.spec = copy.deepcopy(spec) if spec else {"root": None, "elements": {}, "state": {}}
        self.writable = writable  # path prefixes this stream may touch (static mode: ["/state"])
        self.applied = 0

    def push(self, op: dict) -> Optional[str]:
        """Apply one patch; returns an error string instead of raising."""
        path = op.get("path", "")
        if self.writable and not any(path == p or path.startswith(p + "/") for p in self.writable):
            return f"{op.get('op')} {path} refused: this stream may only write {self.writable}"
        try:
            self.spec = apply_op(self.spec, op)
        except PatchError as error:
            return str(error)
        self.applied += 1
        return None


def patch_lines(pieces: Iterator[tuple]) -> Iterator[dict]:
    """JSONL from a streamed model reply -> patch dicts (or {"error"}), each as soon as its line is complete."""
    buffer = ""
    for piece in pieces:
        if piece[0] != "text":
            continue
        buffer += piece[1]
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            yield from _line(line)
    yield from _line(buffer)


def _line(line: str) -> Iterator[dict]:
    line = line.strip()
    if not line or line.startswith("```"):
        return
    try:
        op = json.loads(line)
    except json.JSONDecodeError as error:
        yield {"error": f"not JSON: {error}", "line": line[:100]}
        return
    yield op if isinstance(op, dict) and "op" in op else {"error": "not a JSON Patch operation", "line": line[:100]}


def spec_to_patches(spec: dict) -> List[dict]:
    """A spec as the patch stream a model would write: root, then each element (parents first),
    with each state key emitted right after the first element that reads it."""
    patches = [{"op": "add", "path": "/root", "value": spec["root"]}]
    state = spec.get("state") or {}
    emitted = set()

    def keys_used(el: dict) -> List[str]:
        text = json.dumps(el)
        return [k for k in state if f'"/{k}' in text or "${/" + k in text]

    def visit(eid: str):
        el = spec["elements"][eid]
        patches.append({"op": "add", "path": f"/elements/{escape(eid)}", "value": el})
        for k in keys_used(el):
            if k not in emitted:
                emitted.add(k)
                patches.append({"op": "add", "path": f"/state/{escape(k)}", "value": state[k]})
        for c in el.get("children") or []:
            visit(c)

    visit(spec["root"])
    for k in state:
        if k not in emitted:
            patches.append({"op": "add", "path": f"/state/{escape(k)}", "value": state[k]})
    return patches


def to_jsonl(ops: List[dict]) -> str:
    return "\n".join(json.dumps(o, separators=(",", ":")) for o in ops) + "\n"


def describe(op: dict) -> str:
    if "error" in op:
        return f"REFUSED {op['error']}"
    value = op.get("value")
    if isinstance(value, dict) and "type" in value:
        return f"{op['op']:<7} {op['path']:<28} {value['type']}"
    return f"{op['op']:<7} {op['path']:<28} {short(value, 70)}"


def from_tree(tree: dict, bind: Optional[Dict[str, str]] = None) -> dict:
    """Canonical tree -> json-render spec. Buttons become `on.press` bindings; GeneratedView becomes
    CustomHtml whose html lives in state (so the document streams as one state patch)."""
    elements, state = {}, {}
    counters: dict = {}

    def visit(n: dict, is_root: bool = False) -> str:
        kind = n["type"]
        counters[kind] = counters.get(kind, 0) + 1
        eid = "main" if is_root else f"{kind.lower()}-{counters[kind]}"
        props = dict(n.get("props") or {})
        el: dict = {"type": kind, "props": props, "children": []}
        if kind == "Button":
            action, params = props.pop("action"), props.pop("params", {})
            el["on"] = {"press": {"action": action, "params": params}}
        if kind == "GeneratedView":
            state.setdefault("clock", {})["html"] = props["html"]
            el = {"type": "CustomHtml", "props": {"title": props["title"], "html": {"$state": "/clock/html"},
                                                  "height": props.get("height", 260)}, "children": []}
        if kind == "Metric" and bind and props.get("label") in bind:
            key = bind[props["label"]]
            state.setdefault("summary", {})[key] = props["value"]
            props["value"] = {"$state": f"/summary/{key}"}
        if kind == "Table":
            state["windows"] = props["rows"]
            props["rows"] = {"$state": "/windows"}
        elements[eid] = el
        el["children"] = [visit(c) for c in n.get("children") or []]
        return eid

    root = visit(tree, True)
    return {"root": root, "elements": elements, "state": state}
