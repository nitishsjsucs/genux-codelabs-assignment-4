"""AG-UI · mode 1 · STATIC - the frontend owns the components; the agent picks one and fills its props.

The page declares three *frontend tools* in RunAgentInput.tools
(frontend_tools.json). Each is a component the page already has. The model
"renders UI" by calling one: the server streams TOOL_CALL_START / ARGS / END and
ends the run (it cannot execute a client tool); the page draws the matching
component with the arguments as props, then sends a tool result on the next
run, and the model writes its closing sentence. The model never describes
layout - it only chooses which component and what numbers.

Run:  python3 labs/01_ag_ui/static.py         (offline, scripted model)
      python3 labs/01_ag_ui/static.py --live  (Claude; needs `pip install anthropic`)
"""

from __future__ import annotations

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))  # repo root, for `common`
sys.path.insert(0, str(HERE))

import agui  # noqa: E402
from common import data, fixtures, term  # noqa: E402
from common.llm import get_model, wants_live  # noqa: E402
from common.sse import banner  # noqa: E402

FRONTEND_TOOLS = json.loads((HERE / "frontend_tools.json").read_text())
S = data.summary()

SYSTEM = (
    "You are VoltPilot, a home-energy copilot. The page offers components as tools. "
    "Answer by calling show_energy_summary, show_solar_chart and show_charge_plan once each "
    "with the numbers from the data below, then add one short sentence.\n"
    f"DATA: {json.dumps({'summary': S, 'week': data.WEEK, 'windows': data.CHARGE_WINDOWS})}"
)

SCRIPT = [
    {  # turn 1: pick three components, fill their props
        "text": "Here is your week - three panels coming up.",
        "tool_calls": [
            {"name": "show_energy_summary", "arguments": {
                "solar_kwh": S["solar_kwh"], "solar_delta_pct": S["solar_delta_pct"],
                "self_sufficiency_pct": S["self_sufficiency_pct"], "import_cost": S["import_cost"],
                "battery_pct": S["battery_pct"]}},
            {"name": "show_solar_chart", "arguments": {
                "days": [d["day"] for d in data.WEEK], "solar_kwh": [d["solar"] for d in data.WEEK]}},
            {"name": "show_charge_plan", "arguments": {
                "windows": data.CHARGE_WINDOWS, "recommendation": fixtures.recommendation_text()}},
        ],
    },
    {"text": f"Your best charging window is {S['best_window']}: it saves {data.money(S['saving_vs_peak'])} versus charging at peak."},
]


# The terminal twins of the page's prebuilt components (labs/01_ag_ui/components.js).
def component_tree(name: str, args: dict) -> dict:
    n = fixtures.node
    if name == "show_energy_summary":
        return n("Row", [
            n("Metric", label="Solar generated", value=f"{args['solar_kwh']} kWh", delta=f"+{args['solar_delta_pct']}% vs last week"),
            n("Metric", label="Self-sufficiency", value=f"{args['self_sufficiency_pct']}%"),
            n("Metric", label="Grid import cost", value=data.money(args["import_cost"])),
            n("Metric", label="Home battery", value=f"{args['battery_pct']}%"),
        ])
    if name == "show_solar_chart":
        return n("BarChart", title="Solar generated per day", labels=args["days"], values=args["solar_kwh"], unit="kWh")
    if name == "show_charge_plan":
        return n("Card", [
            n("Table", columns=["Window", "Source", "Est. cost"],
              rows=[[w["window"], w["source"], data.money(w["cost"])] for w in args["windows"]]),
            n("Text", text=args["recommendation"]),
        ], title="When to charge the EV")
    raise KeyError(name)


def run(inp: dict, model):
    return agui.run_agent(inp, model, SYSTEM, server_tools={})


def http(body: dict, delay: float = 0.0, live: bool = False, sub: str = ""):
    return run(body, get_model(SCRIPT, live, delay))


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    model = get_model(SCRIPT, wants_live(argv))
    print(banner("AG-UI · 1 · static - frontend tools render prebuilt components"))
    print(f"user: {data.PROMPT}")
    print(f"frontend declares tools: {[t['name'] for t in FRONTEND_TOOLS]}\n")

    first = agui.run_input([{"id": "u1", "role": "user", "content": data.PROMPT}], tools=FRONTEND_TOOLS)
    events = list(run(first, model))
    print("RUN 1  POST /api/01_ag_ui/static  ->  SSE")
    agui.print_events(events)
    assert not agui.check_sequence(events), agui.check_sequence(events)

    history = [{"id": "u1", "role": "user", "content": data.PROMPT}] + agui.messages_from_events(events)
    print("\nthe page draws one prebuilt component per client tool call:")
    for m in history:
        for call in m.get("toolCalls", []):
            name, args = call["function"]["name"], json.loads(call["function"]["arguments"])
            print(f"\n  <{name}> props={sorted(args)}")
            print("\n".join("    " + line for line in term.to_text(component_tree(name, args)).splitlines()))
            history.append({"id": f"r-{call['id']}", "role": "tool", "toolCallId": call["id"], "content": f"rendered {name}"})

    second = agui.run_input(history, tools=FRONTEND_TOOLS)
    events2 = list(run(second, model))
    print("\nRUN 2  (tool results sent back)  ->  SSE")
    agui.print_events(events2)
    assert not agui.check_sequence(events2), agui.check_sequence(events2)
    print(f"\nchecks: {len(events) + len(events2)} events, lifecycle valid, layout decided by the page")
    return 0


if __name__ == "__main__":
    sys.exit(main())
