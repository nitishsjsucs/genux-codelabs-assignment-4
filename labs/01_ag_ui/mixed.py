"""AG-UI · mode 4 · MIXED - a catalog tree in shared state, with one GeneratedView region and live buttons.

Mixed mode keeps the declarative default (catalog components, validated) and
opens one sandboxed escape hatch where the catalog runs out: the model sends a
whole element map through `render_ui`, and one of its nodes is a
`GeneratedView` whose `html` prop holds the energy clock. The server validates
the tree (catalog + content policy) and publishes it as one STATE_DELTA.

Both kinds of button close the loop the same way: a catalog Button and the
clock's in-frame button each produce {name, params}; the page starts a new run
with forwardedProps.action; the server checks the allow-list; the model calls
`schedule_ev_charge`; the server patches a confirmation into the tree.

Run:  python3 labs/01_ag_ui/mixed.py [--live]
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import agui  # noqa: E402
from common import catalog, data, fixtures, labkit, sandbox, term  # noqa: E402
from common.llm import get_model, wants_live  # noqa: E402
from common.sse import banner  # noqa: E402

S = data.summary()

RENDER_UI = agui.tool_schema(
    "render_ui",
    "Replace the dashboard with an element map {root, elements:{id:{type, props, children:[ids]}}}. "
    "Use catalog components; use GeneratedView (html prop) only for what the catalog cannot draw.",
    {"spec": {"type": "object"}}, ["spec"],
)

SYSTEM = (
    "You are VoltPilot. Answer with one render_ui call: catalog components for the numbers, the chart, "
    "the table and the buttons; one GeneratedView for a 24-hour energy clock. Components:\n"
    + catalog.describe_for_prompt(allow_generated=True)
    + "\nWhen a message starts with [ui-action], carry out that action with the matching tool."
)


def render_ui(args: dict, state: dict):
    spec = args.get("spec") or {}
    try:
        tree = catalog.flat_to_tree(spec)
    except (KeyError, ValueError, TypeError) as error:
        return f"error: not an element map ({error})", [], []
    errors = catalog.validate_tree(tree, allow_generated=True)
    for n in catalog.walk(tree):
        if n["type"] == "GeneratedView":
            errors += [f"GeneratedView {n.get('id')}: document {p}" for p in sandbox.policy_check(n["props"].get("html", ""))]
    if errors:
        return "error: " + "; ".join(errors), [], []
    op = "replace" if "ui" in state else "add"
    return f"rendered {catalog.count(tree)} components", [{"op": op, "path": "/ui", "value": spec}], []


def schedule_ev_charge(args: dict, state: dict):
    booking = labkit.schedule(args.get("window"))
    ops = [
        {"op": "add", "path": "/ev", "value": booking},
        {"op": "add", "path": "/ui/elements/booked", "value": {"type": "Text", "props": {"text": booking["message"], "variant": "success"}, "children": []}},
        {"op": "add", "path": "/ui/elements/root/children/1", "value": "booked"},
    ]
    return booking["message"], ops, []


SCHEDULE = agui.schedule_tool_schema([w["window"] for w in data.CHARGE_WINDOWS])
SERVER_TOOLS = {"render_ui": (RENDER_UI, render_ui), "schedule_ev_charge": (SCHEDULE, schedule_ev_charge)}


def click(history: list, events: list, name: str, params: dict) -> dict:
    return agui.click_input(history, events, name, params, labkit.action_text(name, params))


def script(messages: list) -> dict:
    step, action = labkit.turns_since_user(messages), labkit.parse_action(labkit.last_user(messages))
    if action:
        return {"tool_calls": [{"name": action[0], "arguments": action[1]}]} if step == 0 else {"text": labkit.last_tool_result(messages)}
    if step == 0:
        spec = fixtures.to_flat(fixtures.dashboard_tree(with_actions=True, with_generated=True))
        return {"text": "Numbers from the catalog, plus one clock the catalog cannot draw.",
                "tool_calls": [{"name": "render_ui", "arguments": {"spec": spec}}]}
    return {"text": f"Press 'Schedule {S['best_window']}' - on the card or on the clock - and I will book it."}


def run(inp: dict, model):
    action = (inp.get("forwardedProps") or {}).get("action")
    if action:
        try:
            labkit.check_action(action.get("name"), action.get("params") or {})
        except (PermissionError, ValueError) as error:
            return iter([agui.event("RUN_STARTED", threadId=inp["threadId"], runId=inp["runId"]),
                         agui.event("RUN_ERROR", message=f"action refused: {error}")])
    return agui.run_agent(inp, model, SYSTEM, SERVER_TOOLS, initial_state={})


def http(body: dict, delay: float = 0.0, live: bool = False, sub: str = ""):
    return run(body, get_model(script, live, delay))


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    model = get_model(script, wants_live(argv))
    print(banner("AG-UI · 4 · mixed - catalog tree + one GeneratedView + actions"))
    print(f"user: {data.PROMPT}\n")
    history = [{"id": "u1", "role": "user", "content": data.PROMPT}]
    events = list(run(agui.run_input(history), model))
    print("RUN 1  POST /api/01_ag_ui/mixed  ->  SSE")
    agui.print_events(events)
    assert not agui.check_sequence(events)
    tree = catalog.flat_to_tree(agui.final_state(events)["ui"])
    kinds = sorted({n["type"] for n in catalog.walk(tree)})
    print(f"\nstate.ui: {catalog.count(tree)} components {kinds}")
    print(term.to_text(tree))

    print("\nclick on the catalog Button 'Schedule 10:30-15:00' -> RUN 2")
    events2 = list(run(click(history, events, "schedule_ev_charge", {"window": S["best_window"]}), model))
    agui.print_events(events2)
    assert not agui.check_sequence(events2)
    final = agui.final_state(events + events2)
    after = catalog.flat_to_tree(final["ui"])
    print(f"\nafter the action: {after['children'][1]['props']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
