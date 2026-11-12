"""Harness · mode 3 · OPEN-ENDED - render_html(title, html): an artifact, sandboxed on the web, summarized in a terminal.

The model writes a full HTML document. The tool lints it, saves it under
labs/06_harness/out/artifacts/, and emits an `html` event. The web surface
mounts it in a sandboxed iframe; the terminal surface cannot run HTML, so it
prints a fallback with the artifact path. A click inside the frame comes back
to the same session as an injected [ui-action] turn.

Run:  python3 labs/06_harness/open_ended.py [--live]
"""

from __future__ import annotations

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


def script(messages: list) -> dict:
    step, action = labkit.turns_since_user(messages), labkit.parse_action(labkit.last_user(messages))
    if action:
        return {"tool_calls": [{"name": action[0], "arguments": action[1]}]} if step == 0 else {"text": labkit.last_tool_result(messages)}
    if step == 0:
        return {"text": "The catalog has no radial chart, so here is a custom one.",
                "tool_calls": [{"name": "render_html", "arguments": {"title": "Energy clock", "html": fixtures.energy_clock_html()}}]}
    return {"text": f"The teal arc is {S['best_window']}. Press the button in the clock to book it."}


SYSTEM = hx.system("Draw today's energy as a 24-hour radial clock with render_html.")


def make_harness(surfaces, live: bool = False, delay: float = 0.0) -> Harness:
    return Harness(get_model(script, live, delay), [hx.RENDER_HTML, hx.SCHEDULE], SYSTEM, surfaces)


def http(body: dict, delay: float = 0.0, live: bool = False, sub: str = ""):
    return hx.web_run(lambda s: make_harness(s, live, delay), body, sub)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    print(banner("Harness · 3 · open-ended - render_html, two surfaces"))
    print(f"user: {data.PROMPT}\n")
    h = make_harness([TerminalSurface()], wants_live(argv))
    print_events(h.run(data.PROMPT))
    print("\nthe web surface relays a click from the frame into the same session:")
    print_events(h.inject_action("schedule_ev_charge", {"window": S["best_window"]}))
    print("\nand a forged action never reaches the model:")
    print_events(h.inject_action("open_garage", {}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
