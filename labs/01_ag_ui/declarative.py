"""AG-UI · mode 2 · DECLARATIVE - the UI is shared state; the agent edits it with JSON Patch.

The run starts with a STATE_SNAPSHOT whose `ui` key is an element map with a
single empty Column. The model builds the dashboard by calling the server tool
`add_component(id, parent, type, props)` once per element. The server checks
each call against the catalog (common/catalog.py), and turns an accepted call
into a STATE_DELTA - two RFC 6902 operations: add the element, append its id to
the parent's children. The page applies each delta and repaints, so the
dashboard grows on screen while the model is still "speaking". The model picks
the layout; the catalog limits what it may pick.

Run:  python3 labs/01_ag_ui/declarative.py [--live]
"""

from __future__ import annotations

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import agui  # noqa: E402
from common import catalog, data, fixtures, term  # noqa: E402
from common.jsonpatch import escape  # noqa: E402
from common.llm import get_model, wants_live  # noqa: E402
from common.sse import banner  # noqa: E402

S = data.summary()

INITIAL_STATE = {"ui": {"root": "root", "elements": {"root": {"type": "Column", "props": {"gap": "medium"}, "children": []}}}}

ADD_COMPONENT = agui.tool_schema(
    "add_component",
    "Add one catalog component to the dashboard. Parents must exist before children.",
    {
        "id": {"type": "string", "description": "unique element id"},
        "parent": {"type": "string", "description": "id of an existing container (root, a Card, Row or Column)"},
        "type": {"type": "string", "enum": catalog.DECLARATIVE_ONLY},
        "props": {"type": "object"},
    },
    ["id", "parent", "type", "props"],
)

SYSTEM = (
    "You are VoltPilot. Build a dashboard that answers the user by calling add_component for each element, "
    "parents first, starting under 'root'. Components:\n" + catalog.describe_for_prompt(allow_generated=False)
    + f"\nDATA: {json.dumps({'summary': S, 'week': data.WEEK, 'windows': data.CHARGE_WINDOWS})}"
)


def add_component(args: dict, state: dict):
    elements = state["ui"]["elements"]
    eid, parent = args.get("id"), args.get("parent")
    if not isinstance(eid, str) or not eid or eid in elements:
        return f"error: id {eid!r} is missing or already used", [], []
    if parent not in elements:
        return f"error: parent {parent!r} does not exist yet - add it first", [], []
    if not catalog.CATALOG[elements[parent]["type"]]["children"]:
        return f"error: {elements[parent]['type']} {parent!r} cannot have children", [], []
    candidate = {"type": args.get("type"), "props": args.get("props") or {}, "children": []}
    errors = catalog.validate_tree(candidate, allow_generated=False, path=eid)
    if errors:
        return "error: " + "; ".join(errors), [], []
    ops = [
        {"op": "add", "path": f"/ui/elements/{escape(eid)}", "value": candidate},
        {"op": "add", "path": f"/ui/elements/{escape(parent)}/children/-", "value": eid},
    ]
    return f"added {candidate['type']} {eid} under {parent}", ops, []


def build_calls() -> list:
    """The scripted model's calls: the canonical dashboard, parents before children."""
    flat = fixtures.to_flat(fixtures.dashboard_tree())
    calls = []

    def visit(eid: str):
        for child in flat["elements"][eid]["children"]:
            el = flat["elements"][child]
            calls.append({"name": "add_component", "arguments": {"id": child, "parent": eid, "type": el["type"], "props": el["props"]}})
            visit(child)

    visit(flat["root"])
    return calls


SCRIPT = [
    {"text": "Building your dashboard piece by piece.", "tool_calls": build_calls()},
    {"text": f"Done. Charge {S['best_window']} - it is the cheapest window this week."},
]

SERVER_TOOLS = {"add_component": (ADD_COMPONENT, add_component)}


def run(inp: dict, model):
    return agui.run_agent(inp, model, SYSTEM, SERVER_TOOLS, initial_state=INITIAL_STATE)


def http(body: dict, delay: float = 0.0, live: bool = False, sub: str = ""):
    return run(body, get_model(SCRIPT, live, delay))


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    model = get_model(SCRIPT, wants_live(argv))
    print(banner("AG-UI · 2 · declarative - the UI tree lives in shared state"))
    print(f"user: {data.PROMPT}\n")
    inp = agui.run_input([{"id": "u1", "role": "user", "content": data.PROMPT}], state=INITIAL_STATE)
    events = list(run(inp, model))
    print("RUN 1  POST /api/01_ag_ui/declarative  ->  SSE")
    agui.print_events(events)
    problems = agui.check_sequence(events)
    assert not problems, problems

    state = agui.final_state(events)
    tree = catalog.flat_to_tree(state["ui"])
    deltas = sum(1 for e in events if e["type"] == "STATE_DELTA")
    print(f"\nclient replayed 1 snapshot + {deltas} deltas -> {len(state['ui']['elements'])} elements; catalog errors: {catalog.validate_tree(tree) or 'none'}")
    print("what the page draws (terminal renderer, same tree):\n")
    print(term.to_text(tree))
    return 0


if __name__ == "__main__":
    sys.exit(main())
