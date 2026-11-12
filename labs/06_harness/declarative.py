"""Harness · mode 2 · DECLARATIVE - render_ui(spec), validated; the model repairs its own mistakes.

render_ui takes a whole component tree. The scripted model's first attempt has
two mistakes a real model makes: a component outside the catalog (PieChart) and
a table row with too few cells. The tool does not raise - it returns the
validator's messages as the tool result. On the next step the model reads them
and sends a corrected spec, which renders. Bounded steps (MAX_STEPS = 8) stop a
model that never gets it right.

Run:  python3 labs/06_harness/declarative.py [--live]
"""

from __future__ import annotations

import copy
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import hx_tools as hx  # noqa: E402
from common import data, fixtures, labkit  # noqa: E402
from common.llm import get_model, wants_live  # noqa: E402
from common.sse import banner  # noqa: E402
from harness import Harness, TerminalSurface, print_events  # noqa: E402

S = data.summary()
GOOD = fixtures.dashboard_tree()


def flawed() -> dict:
    spec = copy.deepcopy(GOOD)
    spec["children"][2]["children"][0] = fixtures.node("PieChart", title="Solar share", slices=[71, 29])
    spec["children"][3]["children"][0]["props"]["rows"][2] = ["16:00-20:30", "$15.12"]
    return spec


def script(messages: list) -> dict:
    step, result = labkit.turns_since_user(messages), labkit.last_tool_result(messages)
    if step == 0:
        return {"text": "Building the dashboard.", "tool_calls": [{"name": "render_ui", "arguments": {"spec": flawed()}}]}
    if result.startswith("error"):
        return {"text": "Fixing the spec: BarChart instead of PieChart, and three cells per row.",
                "tool_calls": [{"name": "render_ui", "arguments": {"spec": GOOD}}]}
    return {"text": f"Charge {S['best_window']} - the cheapest window this week."}


SYSTEM = hx.system("Answer with one render_ui call; if it returns an error, fix the spec and call it again.")


def make_harness(surfaces, live: bool = False, delay: float = 0.0) -> Harness:
    return Harness(get_model(script, live, delay), [hx.make_render_ui(allow_generated=False)], SYSTEM, surfaces)


def http(body: dict, delay: float = 0.0, live: bool = False, sub: str = ""):
    return hx.web_run(lambda s: make_harness(s, live, delay), body, sub)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    print(banner("Harness · 2 · declarative - render_ui with a self-correction loop"))
    print(f"user: {data.PROMPT}\n")
    events = print_events(make_harness([TerminalSurface()], wants_live(argv)).run(data.PROMPT))
    errors = [e for e in events if e["kind"] == "tool_result" and not e["ok"]]
    print(f"\n{len(errors)} rejected spec(s), then a valid one: the error text was the model's only feedback")
    return 0


if __name__ == "__main__":
    sys.exit(main())
