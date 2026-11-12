"""MCP Apps · mode 1 · STATIC - a hand-written ui:// view; the tool result carries data only.

`show_energy_dashboard` declares _meta.ui.resourceUri = ui://voltpilot/static-dashboard.html.
The host calls the tool (because its model chose to), reads the resource, and
mounts the developer-written HTML in a sandboxed iframe. The view receives the
result's structuredContent through ui/notifications/tool-result and lays it
out itself. No model writes any UI here - the server does not even need one.

Its "Schedule" button calls `schedule_ev_charge`, a tool with
visibility ["app"]: callable from the view (through the host), invisible to the model.

Run:  python3 labs/03_mcp_apps/static.py
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import mcp_voltpilot as vp  # noqa: E402
from common import data  # noqa: E402
from common.sse import banner  # noqa: E402
from mcp_server import InProcessHost, MCPServer, text_result, ui_tool  # noqa: E402

URI = "ui://voltpilot/static-dashboard.html"


def show_energy_dashboard(args: dict) -> dict:
    s = vp.S
    text = (f"Solar {s['solar_kwh']} kWh (+{s['solar_delta_pct']}%), self-sufficiency {s['self_sufficiency_pct']}%, "
            f"best EV window {s['best_window']}.")  # `content` is for the model; structuredContent is for the view
    return text_result(text, vp.week_payload())


def make_server(live: bool = False, delay: float = 0.0) -> MCPServer:
    tools = [ui_tool("show_energy_dashboard", "Show this week's solar and EV charging dashboard.", {}, [], resource_uri=URI),
             vp.SCHEDULE_TOOL]
    handlers = {"show_energy_dashboard": show_energy_dashboard, "schedule_ev_charge": vp.schedule_handler}
    return MCPServer("voltpilot-static", tools, handlers, {URI: vp.resource("static.html")})


def http(body: dict, delay: float = 0.0, live: bool = False, sub: str = ""):
    return make_server(live, delay).handle(body) or {}


def main(argv=None) -> int:
    print(banner("MCP Apps · 1 · static - developer-written ui:// view, data-only result"))
    host = InProcessHost(make_server())
    host.connect()
    for t in host.tools:
        print(f"  tool {t['name']:<22} _meta.ui={t.get('_meta', {}).get('ui')}")
    print(f"\nhost model picks show_energy_dashboard (model may call: {host.model_may_call('show_energy_dashboard')})")
    result = host.rpc("tools/call", {"name": "show_energy_dashboard", "arguments": {}})
    print(f"  content (for the model): {result['content'][0]['text']}")
    print(f"  structuredContent keys (for the view): {sorted(result['structuredContent'])}")
    v = host.open_view("show_energy_dashboard")
    print(f"\nview {v['uri']}  mimeType={v['mimeType']}  {len(v['html'])} bytes (scripts inlined)")
    print(f"host CSP: {v['csp']}")
    print("\nthe view's Schedule button -> tools/call schedule_ev_charge (visibility ['app'])")
    print(f"  view may call: {host.view_may_call('schedule_ev_charge')}   model may call: {host.model_may_call('schedule_ev_charge')}")
    booked = host.rpc("tools/call", {"name": "schedule_ev_charge", "arguments": {"window": vp.S['best_window']}})
    print(f"  -> {booked['content'][0]['text']}")
    bad = host.rpc("tools/call", {"name": "schedule_ev_charge", "arguments": {"window": "03:00-04:00"}})
    print(f"  bad window -> isError={bad['isError']}: {bad['content'][0]['text'][:90]}")
    print(f"\nuser prompt in the host chat: {data.PROMPT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
