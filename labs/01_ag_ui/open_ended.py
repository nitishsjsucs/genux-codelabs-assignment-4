"""AG-UI · mode 3 · OPEN-ENDED - the model writes HTML; AG-UI carries it in a CUSTOM event.

The catalog has no "24-hour radial energy clock", so the model writes one: a
self-contained HTML document passed to the server tool `render_html`. The
server lints it (common/sandbox.policy_check) and forwards it as an AG-UI
CUSTOM event named `voltpilot.generated_html`. The page mounts it in a
sandboxed iframe (common/web/sandbox.js). AG-UI does not define generated
markup; CUSTOM is the protocol's extension point for app-defined payloads.

The clock has a button. A click inside the frame can only post one message
shape; the page turns an allow-listed action into a *new run* whose input
carries the action (forwardedProps.action + a user message). The server checks
the action again before the model ever sees it.

Run:  python3 labs/01_ag_ui/open_ended.py [--live]
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import agui  # noqa: E402
from common import data, fixtures, labkit, sandbox  # noqa: E402
from common.llm import get_model, wants_live  # noqa: E402
from common.sse import banner  # noqa: E402

S = data.summary()

RENDER_HTML = agui.tool_schema(
    "render_html",
    "Show a self-contained HTML document (inline CSS/JS only, no network) in a sandboxed frame. "
    "Call window.voltpilot.action(name, params) for a button; allowed names: schedule_ev_charge, dismiss.",
    {"title": {"type": "string"}, "html": {"type": "string"}},
    ["title", "html"],
)
SCHEDULE = agui.schedule_tool_schema([w["window"] for w in data.CHARGE_WINDOWS])

SYSTEM = (
    "You are VoltPilot. Draw today's energy as a 24-hour radial clock by calling render_html once. "
    "When a message starts with [ui-action], carry out that action with the matching tool."
)


def render_html(args: dict, state: dict):
    html, title = args.get("html", ""), args.get("title", "Generated view")
    problems = sandbox.policy_check(html)
    if problems:
        return "error: refused by content policy - the document " + ", ".join(problems), [], []
    custom = agui.event("CUSTOM", name="voltpilot.generated_html",
                        value={"title": title, "html": html, "bytes": len(html.encode()), "height": 280})
    return f"mounted {title!r} ({len(html.encode())} bytes) in a sandboxed frame", [], [custom]


def schedule_ev_charge(args: dict, state: dict):
    booking = labkit.schedule(args.get("window"))
    return booking["message"], [{"op": "add", "path": "/ev", "value": booking}], []


SERVER_TOOLS = {"render_html": (RENDER_HTML, render_html), "schedule_ev_charge": (SCHEDULE, schedule_ev_charge)}


def script(messages: list) -> dict:
    step, action = labkit.turns_since_user(messages), labkit.parse_action(labkit.last_user(messages))
    if action:
        if step == 0:
            return {"tool_calls": [{"name": action[0], "arguments": action[1]}]}
        return {"text": labkit.last_tool_result(messages)}
    if step == 0:
        return {"text": "The catalog cannot draw a 24-hour clock, so I wrote one for you.",
                "tool_calls": [{"name": "render_html", "arguments": {"title": "Energy clock", "html": fixtures.energy_clock_html()}}]}
    return {"text": f"The teal arc marks {S['best_window']}, when solar covers most of the charge."}


def run(inp: dict, model):
    action = (inp.get("forwardedProps") or {}).get("action")
    if action:  # the page relayed a click - check it before any model call
        try:
            labkit.check_action(action.get("name"), action.get("params") or {})
        except (PermissionError, ValueError) as error:
            return iter([agui.event("RUN_STARTED", threadId=inp["threadId"], runId=inp["runId"]),
                         agui.event("RUN_ERROR", message=f"action refused: {error}")])
    return agui.run_agent(inp, model, SYSTEM, SERVER_TOOLS, initial_state={})


def http(body: dict, delay: float = 0.0, live: bool = False, sub: str = ""):
    return run(body, get_model(script, live, delay))


def click(history: list, events: list, name: str, params: dict) -> dict:
    """What the page sends when the sandboxed button posts {type:'voltpilot:action', ...}."""
    return agui.click_input(history, events, name, params, labkit.action_text(name, params))


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    model = get_model(script, wants_live(argv))
    print(banner("AG-UI · 3 · open-ended - generated HTML in a CUSTOM event"))
    print(f"user: {data.PROMPT}\n")
    history = [{"id": "u1", "role": "user", "content": data.PROMPT}]
    events = list(run(agui.run_input(history), model))
    print("RUN 1  POST /api/01_ag_ui/open_ended  ->  SSE")
    agui.print_events(events)
    assert not agui.check_sequence(events)
    custom = next(e for e in events if e["type"] == "CUSTOM")
    html = custom["value"]["html"]
    print(f"\nCUSTOM payload: {custom['value']['bytes']} bytes of HTML; policy problems: {sandbox.policy_check(html) or 'none'}")
    print(f"the page mounts it as <iframe sandbox=\"allow-scripts\" srcdoc=...> with CSP: {sandbox.CSP[:60]}...")

    print("\nthe user clicks 'Schedule 10:30-15:00' inside the frame -> postMessage -> page starts RUN 2")
    events2 = list(run(click(history, events, "schedule_ev_charge", {"window": S["best_window"]}), model))
    agui.print_events(events2)
    assert not agui.check_sequence(events2)

    print("\na forged message naming a non-allow-listed action is refused before the model runs:")
    bad = list(run(click(history, events, "delete_account", {}), model))
    agui.print_events(bad)
    return 0


if __name__ == "__main__":
    sys.exit(main())
