"""Harness · mode 1 · STATIC - show_component(name, props) from a fixed set of prebuilt components.

The harness offers one UI tool. Its enum lists three components the app
already has (EnergySummary, SolarChart, ChargePlan); the model picks names and
supplies props, the tool checks the required props and draws on every attached
surface - the terminal here, a page when served. The model cannot invent a
layout: an unknown name is an error result.

Run:  python3 labs/06_harness/static.py [--live]
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import hx_tools as hx  # noqa: E402
from common import data, fixtures  # noqa: E402
from common.llm import get_model, wants_live  # noqa: E402
from common.sse import banner  # noqa: E402
from harness import Harness, TerminalSurface, print_events  # noqa: E402

S = data.summary()
SCRIPT = [
    {"text": "Three panels: your week, solar per day, and the charge plan.", "tool_calls": [
        {"name": "show_component", "arguments": {"name": "EnergySummary", "props": {
            "solar_kwh": S["solar_kwh"], "solar_delta_pct": S["solar_delta_pct"],
            "self_sufficiency_pct": S["self_sufficiency_pct"], "import_cost": S["import_cost"]}}},
        {"name": "show_component", "arguments": {"name": "SolarChart", "props": {
            "days": [d["day"] for d in data.WEEK], "solar_kwh": [d["solar"] for d in data.WEEK]}}},
        {"name": "show_component", "arguments": {"name": "ChargePlan", "props": {
            "windows": data.CHARGE_WINDOWS, "recommendation": fixtures.recommendation_text()}}},
    ]},
    {"text": f"Charge {S['best_window']}; it saves {data.money(S['saving_vs_peak'])} versus peak."},
]
SYSTEM = hx.system("Answer with show_component calls, then one sentence.")


def make_harness(surfaces, live: bool = False, delay: float = 0.0) -> Harness:
    return Harness(get_model(SCRIPT, live, delay), [hx.SHOW_COMPONENT], SYSTEM, surfaces)


def http(body: dict, delay: float = 0.0, live: bool = False, sub: str = ""):
    return hx.web_run(lambda s: make_harness(s, live, delay), body, sub)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    print(banner("Harness · 1 · static - show_component from a fixed set"))
    print(f"user: {data.PROMPT}\n")
    h = make_harness([TerminalSurface()], wants_live(argv))
    print_events(h.run(data.PROMPT))
    print("\nan unknown component is an error result, not a crash:")
    print("  " + hx.show_component({"name": "PieChart", "props": {}}, h))
    return 0


if __name__ == "__main__":
    sys.exit(main())
