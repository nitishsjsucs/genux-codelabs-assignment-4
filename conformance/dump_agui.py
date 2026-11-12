"""Write every AG-UI event and RunAgentInput our server produces (all four modes, actions included)
to out/agui_events.json, for agui.mjs to validate with the official @ag-ui/core schemas."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from common import data, registry  # noqa: E402
from common.llm import ScriptedModel  # noqa: E402

registry.load("01_ag_ui", "static")
import agui  # noqa: E402

PROMPT = [{"id": "u1", "role": "user", "content": data.PROMPT}]
runs = []
for mode in ("static", "declarative", "open_ended", "mixed"):
    m = registry.load("01_ag_ui", mode)
    script = getattr(m, "SCRIPT", None) or m.script
    model = ScriptedModel(script)
    tools = getattr(m, "FRONTEND_TOOLS", [])
    first = agui.run_input(PROMPT, state=getattr(m, "INITIAL_STATE", {}), tools=tools)
    events = list(m.run(first, model))
    runs.append({"mode": mode, "input": first, "events": events})
    if mode == "static":
        history = PROMPT + agui.messages_from_events(events)
        history += [{"id": f"r-{c['id']}", "role": "tool", "toolCallId": c["id"], "content": "rendered"}
                    for msg in history for c in msg.get("toolCalls", [])]
        second = agui.run_input(history, tools=tools)
        runs.append({"mode": "static/run2", "input": second, "events": list(m.run(second, model))})
    if mode in ("open_ended", "mixed"):
        click = m.click(PROMPT, events, "schedule_ev_charge", {"window": "10:30-15:00"})
        runs.append({"mode": f"{mode}/action", "input": click, "events": list(m.run(click, model))})

out = Path(__file__).resolve().parent / "out"
out.mkdir(exist_ok=True)
(out / "agui_events.json").write_text(json.dumps(runs))
print(f"wrote {sum(len(r['events']) for r in runs)} events from {len(runs)} runs to conformance/out/agui_events.json")
