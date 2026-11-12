"""OpenUI Lang · mode 3 · OPEN-ENDED - an HtmlArtifact statement carries a whole HTML document.

HtmlArtifact(title, document, height) is OpenUI's escape hatch: the document
is one double-quoted string (line breaks escaped as \\n). The relay checks the
document with the content policy when its statement completes - before the
page mounts it in a sandboxed iframe - and drops the statement if it fails.

Run:  python3 labs/05_openui/open_ended.py [--live]
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import openui  # noqa: E402
import oui_lab as lab  # noqa: E402
from common import data, fixtures, labkit  # noqa: E402
from common.llm import get_model, wants_live  # noqa: E402
from common.sse import banner  # noqa: E402

PROGRAM = (
    'root = Card("Today on the clock", [note, clock], "HtmlArtifact - model-written, sandboxed")\n'
    'note = Text("No catalog component draws a 24-hour radial view, so the model wrote one.", "caption")\n'
    f'clock = HtmlArtifact("Energy clock", {openui.lit(fixtures.energy_clock_html())}, 280)\n'
)
SYSTEM = lab.system_prompt(open_ended=True, extra="Draw a 24-hour radial energy clock in one HtmlArtifact.")


def script(messages: list) -> dict:
    action = labkit.parse_action(labkit.last_user(messages))
    if action:
        return {"text": lab.action_program(action[0], action[1], lab.root_with_booked(PROGRAM))}
    return {"text": PROGRAM}


def run(model):
    program = openui.Program()
    yield from lab.relay(model.stream([{"role": "user", "content": data.PROMPT}], system=SYSTEM), program)
    yield lab.finish(program, allow_generated=True)


def http(body: dict, delay: float = 0.0, live: bool = False, sub: str = ""):
    model = get_model(script, live, delay)
    if sub == "action":
        return lab.handle_action(body, model, SYSTEM)
    return run(model)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    print(banner("OpenUI Lang · 3 · open-ended - HtmlArtifact in a sandbox"))
    lab.print_stream(list(run(get_model(script, wants_live(argv)))), allow_generated=True)
    print("\nthe artifact's button -> POST .../open_ended/action; the model replies with two statements:")
    reply = lab.reply_text(lab.handle_action({"action": "schedule_ev_charge", "params": {"window": "10:30-15:00"}}, get_model(script), SYSTEM))
    print("  " + reply.rstrip().replace("\n", "\n  "))
    print("\nan artifact that loads a remote script is dropped before the page sees it:")
    bad = 'root = Card("x", [a])\na = HtmlArtifact("x", "<script src=\'https://cdn.example/x.js\'></script>")\n'
    lab.print_stream(list(lab.relay(get_model([{"text": bad}]).stream([]), openui.Program())), allow_generated=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
