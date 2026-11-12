"""json-render · mode 1 · STATIC - the developer ships the spec; the model streams state only.

static_spec.json is written by the developer: every value is an expression
({"$state": "/week/importCost"}, {"$template": "${/week/solarKwh} kWh"}). The
app sends it first. The model's whole reply is "replace /state/week/..."
patches; the SpecStream is opened with writable=["/state"], so a patch that
touches /elements or /root is refused - the model cannot alter the layout.

Run:  python3 labs/04_json_render/static.py [--live]
"""

from __future__ import annotations

import json
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

APP_SPEC = json.loads((HERE / "static_spec.json").read_text())
S = data.summary()
STATE = [
    ("/state/week/end", "2026-11-08"),
    ("/state/week/solarKwh", S["solar_kwh"]),
    ("/state/week/deltaPct", S["solar_delta_pct"]),
    ("/state/week/selfPct", S["self_sufficiency_pct"]),
    ("/state/week/importCost", data.money(S["import_cost"])),
    ("/state/week/days", [d["day"] for d in data.WEEK]),
    ("/state/week/solar", [d["solar"] for d in data.WEEK]),
    ("/state/week/advice", fixtures.recommendation_text()),
]
SCRIPT = [{"text": jr.to_jsonl([{"op": "replace", "path": p, "value": v} for p, v in STATE])}]
SYSTEM = jr_lab.system_prompt(False, "The spec already exists; ONLY replace these state paths: " + ", ".join(p for p, _ in STATE))


def run(model):
    stream = jr.SpecStream(APP_SPEC, writable=["/state"])
    yield {"from": "app", "spec": APP_SPEC}
    yield from jr_lab.relay(model.stream([{"role": "user", "content": data.PROMPT}], system=SYSTEM), stream)


def http(body: dict, delay: float = 0.0, live: bool = False, sub: str = ""):
    return run(get_model(SCRIPT, live, delay))


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    print(banner("json-render · 1 · static - app-shipped spec, model streams /state"))
    frames = list(run(get_model(SCRIPT, wants_live(argv))))
    jr_lab.print_frames(frames)
    stream = jr.SpecStream(APP_SPEC, writable=["/state"])
    for f in frames[1:]:
        stream.push(f["patch"])
    jr_lab.print_render(stream.spec, allow_custom=False)
    print("\nthe model tries to add an element in static mode:")
    print("  " + str(stream.push({"op": "add", "path": "/elements/ad", "value": {"type": "Text", "props": {"text": "Buy now"}}})))
    return 0


if __name__ == "__main__":
    sys.exit(main())
