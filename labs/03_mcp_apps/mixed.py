"""MCP Apps · mode 4 · MIXED - a validated catalog spec with one GeneratedView, inside an MCP App.

Same generic renderer view as mode 2, but the server's model may now place one
GeneratedView node (the energy clock) among the catalog components, and the
spec includes Buttons. The view draws catalog nodes directly and the
GeneratedView in a nested sandbox; both kinds of button end in
`tools/call schedule_ev_charge`, which the host allows only because that tool's
visibility includes "app". The result is patched into the view and announced
to the host chat with ui/message.

Run:  python3 labs/03_mcp_apps/mixed.py [--live]
"""

from __future__ import annotations

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import mcp_voltpilot as vp  # noqa: E402
from common import catalog, data, fixtures, term  # noqa: E402
from common.llm import get_model, wants_live  # noqa: E402
from common.sse import banner  # noqa: E402
from mcp_server import InProcessHost, MCPServer, text_result, ui_tool  # noqa: E402

URI = "ui://voltpilot/renderer.html"
SYSTEM = vp.SPEC_SYSTEM.replace("{catalog}", catalog.describe_for_prompt(allow_generated=True)) + (
    "\nUse catalog components for numbers, chart, table and Buttons (actions: schedule_ev_charge, dismiss); "
    "add exactly one GeneratedView with a self-contained HTML 24-hour energy clock.")
SCRIPT = [{"text": json.dumps(fixtures.dashboard_tree(with_actions=True, with_generated=True))}]


def make_server(live: bool = False, delay: float = 0.0) -> MCPServer:
    model = get_model(SCRIPT, live, delay)

    def render_energy_ui(args: dict) -> dict:
        spec = vp.generate_spec(model, SYSTEM, args.get("question") or data.PROMPT, allow_generated=True)
        kinds = sorted({n["type"] for n in catalog.walk(spec)})
        return text_result(f"Rendered {catalog.count(spec)} components ({', '.join(kinds)}).", {"spec": spec})

    tools = [ui_tool("render_energy_ui", "Answer an energy question with a generated dashboard.",
                     {"question": {"type": "string"}}, ["question"], resource_uri=URI), vp.SCHEDULE_TOOL]
    return MCPServer("voltpilot-mixed", tools,
                     {"render_energy_ui": render_energy_ui, "schedule_ev_charge": vp.schedule_handler},
                     {URI: vp.resource("renderer.html")})


def http(body: dict, delay: float = 0.0, live: bool = False, sub: str = ""):
    return make_server(live, delay).handle(body) or {}


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    print(banner("MCP Apps · 4 · mixed - catalog spec + nested GeneratedView + app-only tool"))
    host = InProcessHost(make_server(wants_live(argv)))
    host.connect()
    result = host.rpc("tools/call", {"name": "render_energy_ui", "arguments": {"question": data.PROMPT}})
    spec = result["structuredContent"]["spec"]
    print(f"\n{result['content'][0]['text']}")
    print(term.to_text(spec))
    print("\nclick (catalog Button or nested frame) -> view -> host: may the view call schedule_ev_charge?",
          host.view_may_call("schedule_ev_charge"))
    booked = host.rpc("tools/call", {"name": "schedule_ev_charge", "arguments": {"window": vp.S['best_window']}})
    print(f"  -> {booked['structuredContent']['message']}")
    print(f"and may the host's MODEL call it directly? {host.model_may_call('schedule_ev_charge')} (visibility ['app'])")
    return 0


if __name__ == "__main__":
    sys.exit(main())
