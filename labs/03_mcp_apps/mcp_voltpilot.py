"""VoltPilot's MCP tools and ui:// resources, shared by the four MCP Apps modes."""

from __future__ import annotations

import json
from typing import Optional

from common import catalog, data, labkit, sandbox
from common.llm import collect
from mcp_server import text_result, ui_tool, view

S = data.summary()
INLINE = ["common/web/sandbox.js", "common/web/catalog.js", "labs/03_mcp_apps/views/app_bridge.js"]

# An app-only tool: the model never sees it as callable; a view may call it through the host.
SCHEDULE_TOOL = ui_tool("schedule_ev_charge", "Book the EV charge for one of the offered windows.",
                        {"window": {"type": "string", "enum": [w["window"] for w in data.CHARGE_WINDOWS]}},
                        ["window"], visibility=["app"])


def schedule_handler(args: dict) -> dict:
    booking = labkit.schedule(args.get("window"))
    return text_result(booking["message"], booking)


def resource(name: str, csp: Optional[dict] = None):
    def read() -> dict:
        meta = {"ui": {"prefersBorder": True}}
        if csp:
            meta["ui"]["csp"] = csp
        return {"text": view(name, INLINE), "_meta": meta}
    return read


def week_payload() -> dict:
    return {"summary": S, "week": data.WEEK, "windows": data.CHARGE_WINDOWS}


def extract_json(text: str) -> dict:
    """The first JSON object in a model reply (a live model may wrap it in prose or a code fence)."""
    start = text.find("{")
    if start < 0:
        raise ValueError("the model reply contains no JSON object")
    depth, in_str, esc = 0, False, False
    for i, ch in enumerate(text[start:], start):
        if in_str:
            esc = (ch == "\\") and not esc
            if ch == '"' and not esc:
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError("unterminated JSON object in the model reply")


def generate_spec(model, system: str, question: str, allow_generated: bool) -> dict:
    """Server-side generation: ask the model for a canonical tree, then validate it before it leaves the server."""
    text, _calls = collect(model.stream([{"role": "user", "content": question}], system=system))
    spec = extract_json(text)
    errors = catalog.validate_tree(spec, allow_generated=allow_generated)
    for n in catalog.walk(spec):
        if n.get("type") == "GeneratedView":
            errors += [f"GeneratedView: document {p}" for p in sandbox.policy_check(n["props"].get("html", ""))]
    if errors:
        raise ValueError("invalid spec: " + "; ".join(errors[:5]))
    return spec


SPEC_SYSTEM = (
    "You are VoltPilot's UI generator. Reply with ONE JSON object: a component tree "
    "{\"type\", \"props\", \"children\"} using only these components:\n{catalog}\n"
    "DATA: " + json.dumps(week_payload())
)
