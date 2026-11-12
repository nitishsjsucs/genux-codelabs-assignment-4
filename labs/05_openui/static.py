"""OpenUI Lang · mode 1 · STATIC - developer templates; the model picks one and fills typed slots.

templates/*.oui are OpenUI programs written by the developer with {{slot}}
holes. The model's only move is a tool call, use_template(name, values). The
app checks the slot list and json-encodes every value into a *literal*, so a
value such as "x\"), Button(\"Pay\"" stays a string: the model cannot add a
component, a reference or an action. The filled program then streams to the
page like any other.

Run:  python3 labs/05_openui/static.py [--live]
"""

from __future__ import annotations

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import openui  # noqa: E402
import oui_lab as lab  # noqa: E402
from common import data, fixtures  # noqa: E402
from common.llm import collect, get_model, wants_live  # noqa: E402
from common.sse import banner  # noqa: E402

S = data.summary()
USE_TEMPLATE = {"name": "use_template", "description": "Show one of the app's report templates, filling its slots.",
                "parameters": {"type": "object", "properties": {
                    "name": {"type": "string", "enum": sorted(lab.TEMPLATES)},
                    "values": {"type": "object"}}, "required": ["name", "values"]}}
SYSTEM = "You are VoltPilot. Call use_template once. Templates and their slots: " + json.dumps(
    {t: lab.slots(t) for t in lab.TEMPLATES}) + "\nDATA: " + json.dumps({"summary": S, "week": data.WEEK})
SCRIPT = [{"text": "", "tool_calls": [{"name": "use_template", "arguments": {"name": "weekly_report", "values": {
    "week_label": "Week ending 2026-11-08", "solar": f"{S['solar_kwh']} kWh", "solar_delta": f"+{S['solar_delta_pct']}% vs last week",
    "self_sufficiency": f"{S['self_sufficiency_pct']}%", "import_cost": data.money(S["import_cost"]),
    "days": [d["day"] for d in data.WEEK], "solar_by_day": [d["solar"] for d in data.WEEK],
    "advice": fixtures.recommendation_text()}}}]}]


def run(model, chunk: int = 48):
    _text, calls = collect(model.stream([{"role": "user", "content": data.PROMPT}], tools=[USE_TEMPLATE], system=SYSTEM))
    if not calls:
        yield {"from": "app", "error": "the model did not pick a template"}
        return
    args = json.loads(calls[0]["arguments"])
    try:
        program_text = lab.fill(args.get("name"), args.get("values") or {})
    except ValueError as error:
        yield {"from": "app", "error": str(error)}
        return
    yield {"from": "app", "template": args["name"], "slots": sorted(args["values"])}
    program = openui.Program()
    pieces = (("text", program_text[i:i + chunk]) for i in range(0, len(program_text), chunk))
    yield from lab.relay(pieces, program, source="app")
    yield lab.finish(program, allow_generated=False)


def http(body: dict, delay: float = 0.0, live: bool = False, sub: str = ""):
    return run(get_model(SCRIPT, live, delay))


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    print(banner("OpenUI Lang · 1 · static - developer templates, model fills slots"))
    print(f"templates: { {t: lab.slots(t) for t in lab.TEMPLATES} }\n")
    lab.print_stream(list(run(get_model(SCRIPT, wants_live(argv)))), allow_generated=False)
    print("\nan injection attempt stays a string literal:")
    filled = lab.fill("charge_plan", {"subtitle": 'x"), Button("Pay now", "transfer_funds', "rows": [], "advice": "ok"})
    print("  " + filled.splitlines()[0])
    p = openui.Program()
    p.feed(filled)
    p.close()
    print(f"  parsed root subtitle -> {p.tree()['props'].get('subtitle')!r}; components: {sorted({n['type'] for n in _walk(p.tree())})}")
    return 0


def _walk(n):
    yield n
    for c in n.get("children", []):
        yield from _walk(c)


if __name__ == "__main__":
    sys.exit(main())
