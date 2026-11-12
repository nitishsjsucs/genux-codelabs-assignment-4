"""A2UI · mode 4 · MIXED - catalog dashboard + one HtmlFrame + buttons whose clicks return as A2UI actions.

The model builds the full dashboard on the energy-open catalog: Metrics, a
BarChart, a Table, two Buttons, and one HtmlFrame for the clock. A Button's
action is {event: {name, context}}; the context binds to the data model, so a
click on "Schedule" sends {"window": <value at /ev/bestWindow>}. The page posts
the A2UI action message to /api/02_a2ui/mixed/action; the server checks the
allow-list, hands the action to the model as a user turn, and relays the
model's reply - here one updateDataModel and one updateComponents that inserts
a Callout bound to /ev/status.

Run:  python3 labs/02_a2ui/mixed.py [--live]
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import a2ui  # noqa: E402
import a2ui_surfaces as surf  # noqa: E402
from common import data, labkit  # noqa: E402,F401
from common.llm import get_model, wants_live  # noqa: E402
from common.sse import banner  # noqa: E402

SYSTEM = surf.system_prompt(a2ui.ENERGY_OPEN_CATALOG, "Use catalog components for numbers, chart, table and buttons "
                            "(actions: schedule_ev_charge, dismiss); one HtmlFrame for a 24-hour energy clock. "
                            "When a message starts with [ui-action], answer with updateDataModel /ev/status and "
                            "updateComponents adding a Callout bound to it.")


def script(messages: list) -> dict:
    action = labkit.parse_action(labkit.last_user(messages))
    if action:
        return {"text": a2ui.to_jsonl(surf.action_reply(action[0], action[1], "mixed"))}
    return {"text": a2ui.to_jsonl(surf.mixed_reply())}


def run(model, client: a2ui.Client):
    pieces = model.stream([{"role": "user", "content": data.PROMPT}], system=SYSTEM)
    yield from surf.frames("model", surf.relay(pieces, client))


def on_action(message: dict, model, client=None):
    return surf.handle_action(message, model, SYSTEM, surf.mixed_reply())


def http(body: dict, delay: float = 0.0, live: bool = False, sub: str = ""):
    model, client = get_model(script, live, delay), a2ui.Client()
    if sub == "action":
        return on_action(body, model, client)
    return run(model, client)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    model = get_model(script, wants_live(argv))
    print(banner("A2UI · 4 · mixed - catalog + HtmlFrame + action round trip"))
    print(f"user: {data.PROMPT}\n")
    client = a2ui.Client()
    surf.print_transcript(run(model, client), client)

    tree = client.to_tree(surf.SID)
    button = next(n for n in _walk(tree) if n["type"] == "Button" and n["props"]["action"] == "schedule_ev_charge")
    msg = a2ui.action_message("schedule_ev_charge", surf.SID, button["id"], button["props"]["params"])
    print(f"\nclick -> client sends: {msg}")
    page = a2ui.Client()
    for m in surf.mixed_reply():
        page.apply(m)
    for f in on_action(msg, model):
        print(f"  [{f['from']}] {a2ui.describe(f.get('a2ui') or {'error': f.get('error')})}")
        if "a2ui" in f:
            page.apply(f["a2ui"])
    print(f"\nafter the action, /ev/status = {page.surfaces[surf.SID].data['ev']['status']!r}")
    print(f"root children: {page.surfaces[surf.SID].components['root']['children']}")

    print("\na forged action is refused before the model sees it:")
    for f in on_action(a2ui.action_message("transfer_funds", surf.SID, "btn-schedule", {}), model):
        print(f"  [{f['from']}] {f.get('error')}")
    return 0


def _walk(n):
    yield n
    for c in n.get("children", []):
        yield from _walk(c)


if __name__ == "__main__":
    sys.exit(main())
