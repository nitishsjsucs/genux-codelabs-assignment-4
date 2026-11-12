"""OpenUI Lang · mode 4 · MIXED - catalog statements + one HtmlArtifact + Buttons with actions.

The program mixes catalog components (Stack, Card, Metric, BarChart, Table,
Button) with one HtmlArtifact. A Button's fourth argument is an object of
params - Button("Schedule 10:30-15:00", "schedule_ev_charge", "primary",
{window: "10:30-15:00"}). After a press the model replies with *two
statements*: a new `booked` Text and a re-declared `root` that lists it - a
later statement with the same name replaces the earlier one, so an edit is just
more program.

Run:  python3 labs/05_openui/mixed.py [--live]
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import openui  # noqa: E402
import oui_lab as lab  # noqa: E402
from common import data, labkit, term  # noqa: E402
from common.llm import get_model, wants_live  # noqa: E402
from common.sse import banner  # noqa: E402

PROGRAM = lab.program_for(with_actions=True, with_generated=True)
SYSTEM = lab.system_prompt(open_ended=True, extra="Use catalog components for numbers, chart, table and Buttons "
                           "(actions schedule_ev_charge, dismiss; params as an object); one HtmlArtifact for a 24-hour "
                           "energy clock. After [ui-action], reply with only the statements that change.")


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
    print(banner("OpenUI Lang · 4 · mixed - catalog + HtmlArtifact + actions"))
    program = lab.print_stream(list(run(get_model(script, wants_live(argv)))), allow_generated=True)
    print("\npress 'Schedule 10:30-15:00' -> the model's reply is more program:")
    reply = lab.reply_text(lab.handle_action({"action": "schedule_ev_charge", "params": {"window": "10:30-15:00"}}, get_model(script), SYSTEM))
    print("  " + reply.rstrip().replace("\n", "\n  "))
    program.feed(reply)
    program.close()
    print("\nafter applying it (first 3 lines of the terminal render):")
    print("\n".join(term.to_text(program.tree()).splitlines()[:3]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
