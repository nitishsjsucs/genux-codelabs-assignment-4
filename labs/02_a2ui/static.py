"""A2UI · mode 1 · STATIC - the developer ships the surface; the model only fills its data model.

The app (not the model) sends createSurface and updateComponents from a fixed
TEMPLATE (a2ui_surfaces.py). Every value the template shows is bound to a
data-model path such as {"path": "/report/solar"}. The model's reply may only
contain updateDataModel messages; the server's relay refuses anything else, so
a model cannot change the layout even if it tries.

Run:  python3 labs/02_a2ui/static.py [--live]
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

SYSTEM = surf.system_prompt(a2ui.ENERGY_CATALOG, "The surface already exists. Send ONLY updateDataModel messages for these "
                            "paths: " + ", ".join(p for p, _v in surf.STATIC_DATA))
SCRIPT = [{"text": a2ui.to_jsonl([a2ui.update_data_model(surf.SID, p, v) for p, v in surf.STATIC_DATA])}]
APP_MESSAGES = [a2ui.create_surface(surf.SID, a2ui.ENERGY_CATALOG), a2ui.update_components(surf.SID, surf.TEMPLATE)]


def run(model, client: a2ui.Client):
    for m in APP_MESSAGES:
        client.apply(m)
    yield from surf.frames("app", iter(APP_MESSAGES))
    pieces = model.stream([{"role": "user", "content": data.PROMPT}], system=SYSTEM)
    yield from surf.frames("model", surf.relay(pieces, client, allowed={"updateDataModel"}))


def http(body: dict, delay: float = 0.0, live: bool = False, sub: str = ""):
    return run(get_model(SCRIPT, live, delay), a2ui.Client())


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    print(banner("A2UI · 1 · static - app-shipped surface, model sends data only"))
    print(f"user: {data.PROMPT}\n")
    client = a2ui.Client()
    surf.print_transcript(run(get_model(SCRIPT, wants_live(argv)), client), client)

    print("\npolicy check - the model tries to restructure the surface in static mode:")
    forged = [{"text": a2ui.to_jsonl([a2ui.update_components(surf.SID, [{"id": "title", "component": "Text", "text": "Buy crypto now"}])])}]
    for f in surf.relay(get_model(forged).stream([]), client, allowed={"updateDataModel"}):
        print(f"  [model] {a2ui.describe(f)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
