"""A2UI · mode 2 · DECLARATIVE - the model writes the surface: components, then data.

The model's JSONL reply creates a surface on VoltPilot's energy catalog (basic
catalog + Metric, BarChart, Table, Callout), sends the flat component list in
three updateComponents batches - so the page can draw the header before the
chart arrives - and finally binds the charge-window table through
updateDataModel. The relay validates each line against the catalog before it
reaches the page.

Run:  python3 labs/02_a2ui/declarative.py [--live]
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import a2ui  # noqa: E402
import a2ui_surfaces as surf  # noqa: E402
from common import data  # noqa: E402
from common.llm import get_model, wants_live  # noqa: E402
from common.sse import banner  # noqa: E402

SYSTEM = surf.system_prompt(a2ui.ENERGY_CATALOG, "Create the surface, then components (root first), then data.")
SCRIPT = [{"text": a2ui.to_jsonl(surf.declarative_reply())}]


def run(model, client: a2ui.Client):
    pieces = model.stream([{"role": "user", "content": data.PROMPT}], system=SYSTEM)
    yield from surf.frames("model", surf.relay(pieces, client))


def http(body: dict, delay: float = 0.0, live: bool = False, sub: str = ""):
    return run(get_model(SCRIPT, live, delay), a2ui.Client())


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    print(banner("A2UI · 2 · declarative - model-written components + data model"))
    print(f"user: {data.PROMPT}\n")
    client = a2ui.Client()
    surf.print_transcript(run(get_model(SCRIPT, wants_live(argv)), client), client)

    print("\ncatalog check - a component the energy catalog does not have:")
    bad = [{"text": a2ui.to_jsonl([a2ui.update_components(surf.SID, [{"id": "pie", "component": "PieChart", "slices": [1, 2]}])])}]
    for f in surf.relay(get_model(bad).stream([]), client):
        print(f"  [model] {a2ui.describe(f)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
