"""json-render · mode 4 · MIXED - catalog + CustomHtml + actions, and two renderers for one spec.

The model streams the full dashboard: Metrics bound to /summary/*, a BarChart,
a Table bound to /windows, two Buttons with `on.press` bindings, and one
CustomHtml for the clock. The same final spec is drawn twice: by the web
renderer in the browser and by common/term.py in the terminal (CustomHtml
degrades to a one-line placeholder there). A press posts {action, params};
the server checks it and the model answers with three more patches.

Run:  python3 labs/04_json_render/mixed.py [--live]
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import jr_lab  # noqa: E402
import jsonrender as jr  # noqa: E402
from common import data, term  # noqa: E402
from common.llm import get_model, wants_live  # noqa: E402
from common.sse import banner  # noqa: E402

SPEC = jr_lab.dashboard_spec(with_actions=True, with_generated=True)
SCRIPT = jr_lab.action_script(SPEC)
SYSTEM = jr_lab.system_prompt(True, "Use catalog components for the numbers, chart, table and buttons; "
                              "exactly one CustomHtml for a 24-hour energy clock.")


def run(model):
    stream = jr.SpecStream()
    yield from jr_lab.relay(model.stream([{"role": "user", "content": data.PROMPT}], system=SYSTEM), stream)
    yield {"from": "app", "done": True, "errors": jr.validate(stream.spec, allow_custom=True)}


def http(body: dict, delay: float = 0.0, live: bool = False, sub: str = ""):
    model = get_model(SCRIPT, live, delay)
    if sub == "action":
        return jr_lab.handle_action(body, model, SYSTEM, SPEC)
    return run(model)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    print(banner("json-render · 4 · mixed - catalog + CustomHtml + actions, two renderers"))
    frames = list(run(get_model(SCRIPT, wants_live(argv))))
    patches = [f for f in frames if "patch" in f or "error" in f]
    jr_lab.print_frames(patches, limit=12)
    stream = jr.SpecStream()
    for f in patches:
        stream.push(f["patch"])
    jr_lab.print_render(stream.spec, allow_custom=True)

    print("\npress 'Schedule 10:30-15:00' -> POST /api/04_json_render/mixed/action")
    reply = list(jr_lab.handle_action({"action": "schedule_ev_charge", "params": {"window": "10:30-15:00"}}, get_model(SCRIPT), SYSTEM, SPEC))
    jr_lab.print_frames(reply)
    for f in reply:
        stream.push(f["patch"])
    print("\nterminal renderer after the action (first lines):")
    print("\n".join(term.to_text(jr.to_canonical(stream.spec)).splitlines()[:3]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
