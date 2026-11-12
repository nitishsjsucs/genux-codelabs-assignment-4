"""json-render · mode 2 · DECLARATIVE - the model streams the whole spec as JSON Patch lines.

The reply starts with /root, then adds /elements/<id> parents-first and each
/state value right after the first element that reads it. Every line is
applied the moment it is complete, so the page draws the header before the
table exists; children that have not arrived yet are skipped, not errors.
When the stream ends, the spec is validated against the catalog.

Run:  python3 labs/04_json_render/declarative.py [--live]
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import jr_lab  # noqa: E402
import jsonrender as jr  # noqa: E402
from common import data  # noqa: E402
from common.llm import get_model, wants_live  # noqa: E402
from common.sse import banner  # noqa: E402

SPEC = jr_lab.dashboard_spec()
SCRIPT = [{"text": jr.to_jsonl(jr.spec_to_patches(SPEC))}]
SYSTEM = jr_lab.system_prompt(False)


def run(model):
    stream = jr.SpecStream()
    yield from jr_lab.relay(model.stream([{"role": "user", "content": data.PROMPT}], system=SYSTEM), stream)
    yield {"from": "app", "done": True, "errors": jr.validate(stream.spec)}


def http(body: dict, delay: float = 0.0, live: bool = False, sub: str = ""):
    return run(get_model(SCRIPT, live, delay))


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    print(banner("json-render · 2 · declarative - spec streamed as RFC 6902 patches"))
    frames = list(run(get_model(SCRIPT, wants_live(argv))))
    patches = [f for f in frames if "patch" in f or "error" in f]
    jr_lab.print_frames(patches)
    stream = jr.SpecStream()
    first_paint = None
    for i, f in enumerate(patches):
        stream.push(f["patch"])
        if first_paint is None and len(stream.spec["elements"]) >= 2:
            first_paint = i + 1
    print(f"\n{len(patches)} patch lines; the page can draw after line {first_paint} (root + first element)")
    jr_lab.print_render(stream.spec, allow_custom=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
