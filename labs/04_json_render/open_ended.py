"""json-render · mode 3 · OPEN-ENDED - a CustomHtml element holds a model-written document.

The open catalog adds one type, CustomHtml {title, html, height}. The model
streams a small spec whose CustomHtml takes its html from {"$state":
"/clock/html"}; the document itself arrives as one state patch, which the relay
runs through the content policy before applying. The page renders CustomHtml
in a sandboxed iframe. Its button posts {action, params} to
/api/04_json_render/open_ended/action.

Run:  python3 labs/04_json_render/open_ended.py [--live]
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import jr_lab  # noqa: E402
import jsonrender as jr  # noqa: E402
from common import data, fixtures  # noqa: E402
from common.llm import get_model, wants_live  # noqa: E402
from common.sse import banner  # noqa: E402

SPEC = {
    "root": "main",
    "elements": {
        "main": {"type": "Card", "props": {"title": "Today on the clock", "subtitle": "CustomHtml - model-written, sandboxed"}, "children": ["note", "clock"]},
        "note": {"type": "Text", "props": {"text": "No catalog chart draws a 24-hour radial view, so the model wrote one.", "variant": "caption"}, "children": []},
        "clock": {"type": "CustomHtml", "props": {"title": "Energy clock", "html": {"$state": "/clock/html"}, "height": 280}, "children": []},
    },
    "state": {"clock": {"html": fixtures.energy_clock_html()}},
}
SCRIPT = jr_lab.action_script(SPEC)
SYSTEM = jr_lab.system_prompt(True, "Draw a 24-hour radial energy clock in one CustomHtml element.")


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
    print(banner("json-render · 3 · open-ended - CustomHtml in a sandbox"))
    frames = list(run(get_model(SCRIPT, wants_live(argv))))
    jr_lab.print_frames([f for f in frames if "patch" in f or "error" in f])
    stream = jr.SpecStream()
    for f in frames:
        if "patch" in f:
            stream.push(f["patch"])
    jr_lab.print_render(stream.spec, allow_custom=True)
    print("\nthe frame's button -> POST .../open_ended/action {action: schedule_ev_charge}")
    jr_lab.print_frames(list(jr_lab.handle_action({"action": "schedule_ev_charge", "params": {"window": "10:30-15:00"}}, get_model(SCRIPT), SYSTEM, SPEC)))
    print("\na document that reaches for the network never reaches the page:")
    evil = jr.to_jsonl([{"op": "add", "path": "/state/clock", "value": {"html": "<img src='https://x.example/p.gif'>"}}])
    jr_lab.print_frames(list(jr_lab.relay(get_model([{"text": evil}]).stream([]), jr.SpecStream())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
