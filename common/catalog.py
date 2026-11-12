"""The VoltPilot component catalog - one contract, many wire formats.

Every lab renders the same small set of components. Each technology carries
them differently (an AG-UI state tree, A2UI component messages, a json-render
element map, an OpenUI Lang program, a harness tool argument), but they all
convert to the same *canonical tree* before validation and drawing:

    {"type": "Metric", "props": {"label": "Solar", "value": "133.3 kWh"}, "children": []}

`validate_tree()` is the gate between "the model proposed a UI" and "the
application draws it": unknown components, missing required props, wrong
types and actions outside data.ALLOWED_ACTIONS come back as readable errors -
which a harness can hand to the model as a tool result (labs/06_harness).
"""

from __future__ import annotations

from typing import Any, Dict, List

from common.data import ALLOWED_ACTIONS

# prop name -> (type, required, enum or None). "any" skips the type check.
CATALOG: Dict[str, Dict[str, Any]] = {
    "Card": {"props": {"title": ("str", False, None), "subtitle": ("str", False, None)}, "children": True,
             "doc": "A titled container."},
    "Row": {"props": {"gap": ("str", False, ["small", "medium", "large"])}, "children": True,
            "doc": "Lays children out side by side."},
    "Column": {"props": {"gap": ("str", False, ["small", "medium", "large"])}, "children": True,
               "doc": "Stacks children vertically."},
    "Text": {"props": {"text": ("str", True, None), "variant": ("str", False, ["h1", "h2", "body", "small", "caption", "success"])},
             "children": False, "doc": "One run of text."},
    "Metric": {"props": {"label": ("str", True, None), "value": ("scalar", True, None), "delta": ("str", False, None),
                         "tone": ("str", False, ["good", "bad", "neutral"])},
               "children": False, "doc": "One key number with a label and an optional change."},
    "BarChart": {"props": {"title": ("str", True, None), "labels": ("list[str]", True, None),
                           "values": ("list[num]", True, None), "unit": ("str", False, None)},
                 "children": False, "doc": "One bar series; labels and values have the same length."},
    "Table": {"props": {"columns": ("list[str]", True, None), "rows": ("list[list]", True, None)},
              "children": False, "doc": "A table; every row has one cell per column."},
    "Button": {"props": {"label": ("str", True, None), "action": ("str", True, None), "params": ("dict", False, None),
                         "variant": ("str", False, ["primary", "secondary"])},
               "children": False, "doc": "Fires a named, allow-listed action."},
    # The escape hatch: an open-ended region inside a declarative layout.
    "GeneratedView": {"props": {"title": ("str", True, None), "html": ("str", True, None), "height": ("num", False, None)},
                      "children": False, "doc": "Model-written HTML, mounted in a sandboxed iframe."},
}

DECLARATIVE_ONLY = [name for name in CATALOG if name != "GeneratedView"]


def _type_ok(value: Any, kind: str) -> bool:
    if kind == "any":
        return True
    if kind == "str":
        return isinstance(value, str)
    if kind == "num":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "scalar":
        return isinstance(value, (str, int, float)) and not isinstance(value, bool)
    if kind == "dict":
        return isinstance(value, dict)
    if kind == "list[str]":
        return isinstance(value, list) and all(isinstance(v, str) for v in value)
    if kind == "list[num]":
        return isinstance(value, list) and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)
    if kind == "list[list]":
        return isinstance(value, list) and all(isinstance(v, list) for v in value)
    raise ValueError(kind)


def validate_tree(node: Any, allow_generated: bool = True, path: str = "root") -> List[str]:
    """Every problem in a canonical tree, as 'path: message' strings. [] means drawable."""
    errors: List[str] = []
    if not isinstance(node, dict) or "type" not in node:
        return [f"{path}: expected an object with a 'type'"]
    kind = node["type"]
    spec = CATALOG.get(kind)
    if spec is None or (kind == "GeneratedView" and not allow_generated):
        allowed = ", ".join(CATALOG if allow_generated else DECLARATIVE_ONLY)
        return [f"{path}: unknown component {kind!r}; use one of: {allowed}"]
    props = node.get("props") or {}
    if not isinstance(props, dict):
        return [f"{path}: props must be an object"]
    for name, (ptype, required, enum) in spec["props"].items():
        if name not in props or props[name] is None:
            if required:
                errors.append(f"{path} ({kind}): missing required prop {name!r}")
            continue
        value = props[name]
        if not _type_ok(value, ptype):
            errors.append(f"{path} ({kind}): prop {name!r} should be {ptype}, got {type(value).__name__}")
        elif enum and value not in enum:
            errors.append(f"{path} ({kind}): prop {name!r} must be one of {enum}, got {value!r}")
    for name in props:
        if name not in spec["props"]:
            errors.append(f"{path} ({kind}): unknown prop {name!r}")
    if kind == "BarChart" and isinstance(props.get("labels"), list) and isinstance(props.get("values"), list):
        if len(props["labels"]) != len(props["values"]):
            errors.append(f"{path} (BarChart): {len(props['labels'])} labels but {len(props['values'])} values")
    if kind == "Table" and isinstance(props.get("columns"), list) and isinstance(props.get("rows"), list):
        for i, row in enumerate(props["rows"]):
            if isinstance(row, list) and len(row) != len(props["columns"]):
                errors.append(f"{path} (Table): row {i} has {len(row)} cells for {len(props['columns'])} columns")
    if kind == "Button" and isinstance(props.get("action"), str) and props["action"] not in ALLOWED_ACTIONS:
        errors.append(f"{path} (Button): action {props['action']!r} is not allowed; allowed: {sorted(ALLOWED_ACTIONS)}")
    children = node.get("children") or []
    if children and not spec["children"]:
        errors.append(f"{path} ({kind}): takes no children")
    for i, child in enumerate(children):
        errors.extend(validate_tree(child, allow_generated, f"{path}.{kind}[{i}]"))
    return errors


def count(node: dict) -> int:
    return 1 + sum(count(c) for c in node.get("children") or [])


def walk(node: dict):
    yield node
    for child in node.get("children") or []:
        yield from walk(child)


def flat_to_tree(spec: dict, root_key: str = "root", elements_key: str = "elements") -> dict:
    """{root, elements:{id:{type, props, children:[ids]}}} -> canonical nested tree.

    Missing children (still streaming) are skipped, so a half-built spec renders.
    """
    elements = spec.get(elements_key) or {}

    def build(eid: str, seen: frozenset) -> dict:
        if eid in seen:
            raise ValueError(f"cycle at {eid}")
        el = elements[eid]
        kids = [build(c, seen | {eid}) for c in el.get("children") or [] if c in elements]
        return {"type": el.get("type"), "props": dict(el.get("props") or {}), "children": kids, "id": eid}

    root = spec.get(root_key)
    if root not in elements:
        return {"type": "Column", "props": {}, "children": []}
    return build(root, frozenset())


def describe_for_prompt(allow_generated: bool = True) -> str:
    """The catalog as the lines a system prompt shows the model."""
    lines = []
    for name, spec in CATALOG.items():
        if name == "GeneratedView" and not allow_generated:
            continue
        props = ", ".join(
            f"{p}{'' if req else '?'}: {('|'.join(repr(e) for e in enum)) if enum else t}"
            for p, (t, req, enum) in spec["props"].items()
        )
        kids = " (has children)" if spec["children"] else ""
        lines.append(f"- {name} {{ {props} }}{kids} - {spec['doc']}")
    return "\n".join(lines)
