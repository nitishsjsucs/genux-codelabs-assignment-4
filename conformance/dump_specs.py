"""Write the OpenUI programs and json-render specs our labs produce to out/, for formats.mjs."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from common import registry  # noqa: E402
from common.llm import ScriptedModel  # noqa: E402

out = Path(__file__).resolve().parent / "out"
out.mkdir(exist_ok=True)

programs = {}
for mode in ("static", "declarative", "open_ended", "mixed"):
    m = registry.load("05_openui", mode)
    script = getattr(m, "SCRIPT", None) or m.script
    programs[mode] = "".join(f.get("chunk", "") for f in m.run(ScriptedModel(script)))
(out / "openui_programs.json").write_text(json.dumps(programs))

registry.load("04_json_render", "static")
import jsonrender as jr  # noqa: E402

specs = {}
for mode in ("static", "declarative", "open_ended", "mixed"):
    m = registry.load("04_json_render", mode)
    stream = None
    for f in m.run(ScriptedModel(getattr(m, "SCRIPT", None) or m.script)):
        if "spec" in f:
            stream = jr.SpecStream(f["spec"])
        elif "patch" in f:
            stream = stream or jr.SpecStream()
            stream.push(f["patch"])
    specs[mode] = {"spec": stream.spec, "canonical": jr.to_canonical(stream.spec)}
(out / "json_render_specs.json").write_text(json.dumps(specs))
print(f"wrote {len(programs)} OpenUI programs and {len(specs)} json-render specs to conformance/out/")
