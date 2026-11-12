"""Harness · mode 4 · MIXED - render_ui with a GeneratedView + web-surface actions injected into the loop.

The model renders one validated tree with catalog components, Buttons and one
GeneratedView. The terminal surface draws the catalog part and a placeholder
for the generated region; the web surface draws both. A click on either kind
of button is checked by the server and injected as a [ui-action] turn into the
same harness session; the model calls schedule_ev_charge, whose tool patches a
confirmation into the harness-owned UI state and re-renders every surface.

Run:  python3 labs/06_harness/mixed.py [--live]
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
        return {"text": "Catalog components for the numbers, one generated clock.",
                "tool_calls": [{"name": "render_ui", "arguments": {"spec": fixtures.dashboard_tree(with_actions=True, with_generated=True)}}]}
    return {"text": f"Press 'Schedule {S['best_window']}' on the card or the clock and I will book it."}


SYSTEM = hx.system("Answer with one render_ui call: catalog components plus one GeneratedView energy clock.")


def make_harness(surfaces, live: bool = False, delay: float = 0.0) -> Harness:
    return Harness(get_model(script, live, delay), [hx.make_render_ui(allow_generated=True), hx.SCHEDULE], SYSTEM, surfaces)


def http(body: dict, delay: float = 0.0, live: bool = False, sub: str = ""):
    return hx.web_run(lambda s: make_harness(s, live, delay), body, sub)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    print(banner("Harness · 4 · mixed - render_ui + GeneratedView + injected actions"))
    print(f"user: {data.PROMPT}\n")
    h = make_harness([TerminalSurface()], wants_live(argv))
    print_events(h.run(data.PROMPT))
    print("\nweb surface click -> POST /api/06_harness/mixed/action {session, action, params}")
    print_events(h.inject_action("schedule_ev_charge", {"window": S["best_window"]}))
    print(f"\nsession messages: {len(h.messages)} (user, assistant, tool, [ui-action] user, ...)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
