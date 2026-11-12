"""OpenUI Lang · mode 2 · DECLARATIVE - the model writes the program; the page parses it as it streams.

The reply starts with `root = Stack([title, row1, chart_card, ev_card], ...)`:
four references to names that do not exist yet. The streaming parser draws
four placeholders immediately and replaces each one as its statement
arrives - the transcript prints "pending refs" after every line so you can
watch the count rise and fall to zero. Compared with JSON, every statement is
short and complete on its own line, which is the format's token advantage.

Run:  python3 labs/05_openui/declarative.py [--live]
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
from common.llm import get_model, wants_live  # noqa: E402
from common.sse import banner  # noqa: E402

PROGRAM = lab.program_for()
SCRIPT = [{"text": PROGRAM}]
SYSTEM = lab.system_prompt(open_ended=False)


def run(model):
    program = openui.Program()
    yield from lab.relay(model.stream([{"role": "user", "content": data.PROMPT}], system=SYSTEM), program)
    yield lab.finish(program, allow_generated=False)


def http(body: dict, delay: float = 0.0, live: bool = False, sub: str = ""):
    return run(get_model(SCRIPT, live, delay))


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    print(banner("OpenUI Lang · 2 · declarative - model-written program, streamed"))
    lab.print_stream(list(run(get_model(SCRIPT, wants_live(argv)))), allow_generated=False)
    as_json = json.dumps(fixtures.to_flat(fixtures.dashboard_tree()))
    print(f"\nsize: OpenUI program {len(PROGRAM)} chars vs the same UI as a JSON element map {len(as_json)} chars "
          f"({100 * (1 - len(PROGRAM) / len(as_json)):.0f}% smaller; characters, not tokens)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
