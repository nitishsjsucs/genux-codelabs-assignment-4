"""MCP Apps · mode 2 · DECLARATIVE - the server's model writes a spec; a generic ui:// view renders it.

`render_energy_ui(question)` runs a model *inside the MCP server* to produce a
component tree, validates it against the catalog before it leaves the server,
and returns it in structuredContent.spec. The ui://voltpilot/renderer.html view
contains only the catalog renderer - it draws whatever valid spec arrives.

Run:  python3 labs/03_mcp_apps/declarative.py [--live]
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
SYSTEM = vp.SPEC_SYSTEM.replace("{catalog}", catalog.describe_for_prompt(allow_generated=False))
SCRIPT = [{"text": json.dumps(fixtures.dashboard_tree())}]


def make_server(live: bool = False, delay: float = 0.0) -> MCPServer:
    model = get_model(SCRIPT, live, delay)

    def render_energy_ui(args: dict) -> dict:
        spec = vp.generate_spec(model, SYSTEM, args.get("question") or data.PROMPT, allow_generated=False)
        return text_result(f"Rendered a dashboard with {catalog.count(spec)} components.", {"spec": spec})

    tools = [ui_tool("render_energy_ui", "Answer an energy question with a generated dashboard.",
                     {"question": {"type": "string"}}, ["question"], resource_uri=URI), vp.SCHEDULE_TOOL]
    return MCPServer("voltpilot-declarative", tools,
                     {"render_energy_ui": render_energy_ui, "schedule_ev_charge": vp.schedule_handler},
                     {URI: vp.resource("renderer.html")})


def http(body: dict, delay: float = 0.0, live: bool = False, sub: str = ""):
    return make_server(live, delay).handle(body) or {}


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    print(banner("MCP Apps · 2 · declarative - server-side model writes a validated spec"))
    host = InProcessHost(make_server(wants_live(argv)))
    host.connect()
    result = host.rpc("tools/call", {"name": "render_energy_ui", "arguments": {"question": data.PROMPT}})
    spec = result["structuredContent"]["spec"]
    print(f"\nspec: {catalog.count(spec)} components, catalog errors: {catalog.validate_tree(spec, allow_generated=False) or 'none'}")
    v = host.open_view("render_energy_ui")
    print(f"view {v['uri']} ({len(v['html'])} bytes) - a generic renderer; what it will draw:\n")
    print(term.to_text(spec))
    return 0


if __name__ == "__main__":
    sys.exit(main())
