"""A2UI · mode 3 · OPEN-ENDED - generated HTML through a custom catalog's HtmlFrame.

A2UI has no component that runs arbitrary markup - by design, an agent can
only name components the client already trusts. VoltPilot's *energy-open*
catalog (its own catalogId) adds one: HtmlFrame{title, html, height}, which our
renderer mounts in a sandboxed iframe. The model creates a surface on that
catalog, places an HtmlFrame bound to /clock/html, and sends the document
through updateDataModel - structure and generated content stay separate.

Run:  python3 labs/02_a2ui/open_ended.py [--live]
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import a2ui  # noqa: E402
import a2ui_surfaces as surf  # noqa: E402
from common import data, labkit, sandbox  # noqa: E402
from common.llm import get_model, wants_live  # noqa: E402
from common.sse import banner  # noqa: E402

SYSTEM = surf.system_prompt(a2ui.ENERGY_OPEN_CATALOG, "Draw a 24-hour radial energy clock as a self-contained HTML "
                            "document (inline CSS/JS, no network) in one HtmlFrame bound to /clock/html.")


def script(messages: list) -> dict:
    action = labkit.parse_action(labkit.last_user(messages))
    if action:  # the clock's own button was pressed
        return {"text": a2ui.to_jsonl(surf.action_reply(action[0], action[1], "open_ended"))}
    return {"text": a2ui.to_jsonl(surf.open_ended_reply())}


SCRIPT = script


def checked(stream):
    """Generated HTML gets the content policy on top of the catalog check."""
    for f in stream:
        body = (f.get("a2ui") or {}).get("updateDataModel") or {}
        if body.get("path") == "/clock/html":
            problems = sandbox.policy_check(body.get("value", ""))
            if problems:
                yield {"from": f["from"], "error": "HtmlFrame document refused: " + ", ".join(problems)}
                continue
        yield f


def run(model, client: a2ui.Client):
    pieces = model.stream([{"role": "user", "content": data.PROMPT}], system=SYSTEM)
    yield from checked(surf.frames("model", surf.relay(pieces, client)))


def http(body: dict, delay: float = 0.0, live: bool = False, sub: str = ""):
    model = get_model(SCRIPT, live, delay)
    if sub == "action":  # the HtmlFrame's button, relayed by the page as an A2UI action
        return surf.handle_action(body, model, SYSTEM, surf.open_ended_reply())
    return run(model, a2ui.Client())


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    print(banner("A2UI · 3 · open-ended - HtmlFrame from a custom catalog"))
    print(f"user: {data.PROMPT}\n")
    client = a2ui.Client()
    surf.print_transcript(run(get_model(SCRIPT, wants_live(argv)), client), client)
    html = client.surfaces[surf.SID].data["clock"]["html"]
    print(f"\n/clock/html: {len(html.encode())} bytes, policy problems: {sandbox.policy_check(html) or 'none'}")

    print("\nthe same HtmlFrame on the BASIC catalog is refused - it is not a basic component:")
    basic = a2ui.Client()
    basic.apply(a2ui.create_surface("s2", a2ui.BASIC_CATALOG))
    print("  " + "; ".join(basic.apply(a2ui.update_components("s2", [{"id": "root", "component": "HtmlFrame", "title": "x", "html": "<b>x</b>"}]))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
