"""A stdlib MCP server with MCP Apps UI resources, plus an in-process host for the demos.

MCP Apps (the `io.modelcontextprotocol/ui` extension, SEP-1865) lets an MCP
tool come with an interface:

  * the tool's definition carries  _meta.ui.resourceUri = "ui://..."
  * resources/read on that URI returns HTML with mimeType "text/html;profile=mcp-app"
  * the HOST (Claude Desktop, Goose, our host.js...) mounts that HTML in a
    sandboxed iframe and talks to it with JSON-RPC over postMessage:
    ui/initialize, ui/notifications/tool-input, ui/notifications/tool-result,
    and lets the view call tools/call - but only tools whose
    _meta.ui.visibility includes "app".

This module is the server side - JSON-RPC 2.0 methods initialize, ping,
tools/list, tools/call, resources/list, resources/read - over two transports:
HTTP (serve.py routes POST /api/03_mcp_apps/<mode> here) and stdio
(`python3 labs/03_mcp_apps/mcp_server.py --stdio --mode mixed`), the transport
desktop hosts launch.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

PROTOCOL_VERSION = "2025-06-18"
APP_MIME = "text/html;profile=mcp-app"
UI_EXTENSION = "io.modelcontextprotocol/ui"

# The CSP a host applies when a resource declares no extra domains (mirrors bridge.js).
RESTRICTIVE_CSP = {
    "default-src": ["'none'"], "script-src": ["'self'", "'unsafe-inline'"], "style-src": ["'self'", "'unsafe-inline'"],
    "img-src": ["'self'", "data:"], "font-src": ["'self'"], "connect-src": ["'none'"], "frame-src": ["'none'"],
    "object-src": ["'none'"], "base-uri": ["'self'"],
}


def csp_for(ui_meta: Optional[dict]) -> str:
    directives = {k: list(v) for k, v in RESTRICTIVE_CSP.items()}
    csp = (ui_meta or {}).get("csp") or {}
    for name, key in (("connect-src", "connectDomains"), ("frame-src", "frameDomains")):
        domains = [d for d in csp.get(key) or [] if isinstance(d, str) and not re.search(r"[;\s'\"]", d)]
        if domains:
            directives[name] = [v for v in directives[name] if v != "'none'"] + domains
    return "; ".join(f"{k} {' '.join(v)}" for k, v in directives.items())


# ------------------------------------------------------------------ views: HTML with inlined scripts

def bundle(*paths: str) -> str:
    """Inline ES modules as one classic script: drop import lines and `export` keywords.

    A view runs in a sandboxed srcdoc frame under a CSP with no network, so it
    cannot fetch its scripts - everything it runs must be in the resource itself.
    """
    out = []
    for rel in paths:
        src = (ROOT / rel).read_text()
        src = re.sub(r"^import .*?;\s*$", "", src, flags=re.M)
        src = re.sub(r"^export (default )?", "", src, flags=re.M)
        src = src.replace("</script", "<\\/script")  # an inline script ends at the first </script
        out.append(f"// ---- inlined from {rel}\n{src}")
    return "\n".join(out)


def view(name: str, scripts: List[str]) -> str:
    html = (HERE / "views" / name).read_text()
    css = (ROOT / "common" / "web" / "style.css").read_text()
    return html.replace("/*__STYLE__*/", css).replace("/*__SCRIPTS__*/", bundle(*scripts))


# ------------------------------------------------------------------ the server

Tool = dict           # {name, description, inputSchema, _meta}
Handler = Callable[[dict], dict]   # arguments -> CallToolResult


class MCPServer:
    def __init__(self, name: str, tools: List[Tool], handlers: Dict[str, Handler], resources: Dict[str, Callable[[], dict]]):
        self.name = name
        self.tools = tools
        self.handlers = handlers
        self.resources = resources  # uri -> () -> {"text": html, "_meta": {...}}

    def handle(self, message: dict) -> Optional[dict]:
        """One JSON-RPC message in, one response out (None for notifications)."""
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
            return {"jsonrpc": "2.0", "id": message.get("id") if isinstance(message, dict) else None,
                    "error": {"code": -32600, "message": "invalid request"}}
        method, params, mid = message["method"], message.get("params") or {}, message.get("id")
        if mid is None:  # notification, e.g. notifications/initialized
            return None
        try:
            result = self.dispatch(method, params)
        except KeyError as error:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": str(error).strip("'")}}
        except NotImplementedError:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def dispatch(self, method: str, params: dict) -> dict:
        if method == "initialize":
            client_ui = ((params.get("capabilities") or {}).get("extensions") or {}).get(UI_EXTENSION)
            return {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}, "resources": {}, "extensions": {UI_EXTENSION: {"mimeTypes": [APP_MIME]}}},
                "serverInfo": {"name": self.name, "version": "1.0.0"},
                "instructions": "VoltPilot energy tools." + ("" if client_ui else " (Host did not offer MCP Apps: UI resources will be ignored.)"),
            }
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": self.tools}
        if method == "tools/call":
            name = params.get("name")
            if name not in self.handlers:
                raise KeyError(f"unknown tool: {name}")
            try:
                return self.handlers[name](params.get("arguments") or {})
            except Exception as error:  # noqa: BLE001 - a failed tool is a result, not a protocol error
                return {"content": [{"type": "text", "text": f"error: {error}"}], "isError": True}
        if method == "resources/list":
            return {"resources": [{"uri": uri, "name": uri.rsplit("/", 1)[-1], "mimeType": APP_MIME} for uri in self.resources]}
        if method == "resources/read":
            uri = params.get("uri")
            if uri not in self.resources:
                raise KeyError(f"unknown resource: {uri}")
            res = self.resources[uri]()
            return {"contents": [{"uri": uri, "mimeType": APP_MIME, "text": res["text"], "_meta": res.get("_meta", {})}]}
        raise NotImplementedError(method)


def ui_tool(name: str, description: str, properties: dict, required: List[str], resource_uri: Optional[str] = None,
            visibility: Optional[List[str]] = None) -> Tool:
    ui: dict = {}
    if resource_uri:
        ui["resourceUri"] = resource_uri
    if visibility:
        ui["visibility"] = visibility
    tool = {"name": name, "description": description,
            "inputSchema": {"type": "object", "properties": properties, "required": required}}
    if ui:
        tool["_meta"] = {"ui": ui}
    return tool


def text_result(text: str, structured: Optional[dict] = None) -> dict:
    result = {"content": [{"type": "text", "text": text}], "isError": False}
    if structured is not None:
        result["structuredContent"] = structured
    return result


# ------------------------------------------------------------------ an in-process host (the demos' stand-in for host.js)

class InProcessHost:
    """Does what a host does around a server, minus the iframe: the handshake, the tool call
    the host's model chose, the resource read, and the visibility check for calls from the view."""

    def __init__(self, server: MCPServer, log: Callable[[str], None] = print):
        self.server, self.log, self.next_id, self.tools = server, log, 1, []

    def rpc(self, method: str, params: Optional[dict] = None) -> dict:
        msg = {"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params or {}}
        self.next_id += 1
        reply = self.server.handle(msg)
        brief = json.dumps(reply.get("result", reply.get("error")), separators=(",", ":"))
        self.log(f"  host -> server  {method:<15} <- {brief[:96]}{'...' if len(brief) > 96 else ''}")
        if "error" in reply:
            raise RuntimeError(reply["error"]["message"])
        return reply["result"]

    def connect(self) -> dict:
        init = self.rpc("initialize", {"protocolVersion": PROTOCOL_VERSION, "clientInfo": {"name": "voltpilot-host", "version": "1.0"},
                                       "capabilities": {"extensions": {UI_EXTENSION: {"mimeTypes": [APP_MIME]}}}})
        self.server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.tools = self.rpc("tools/list")["tools"]
        return init

    def model_may_call(self, name: str) -> bool:
        tool = next((t for t in self.tools if t["name"] == name), None)
        return bool(tool) and "model" in tool.get("_meta", {}).get("ui", {}).get("visibility", ["model", "app"])

    def view_may_call(self, name: str) -> bool:
        tool = next((t for t in self.tools if t["name"] == name), None)
        return bool(tool) and "app" in tool.get("_meta", {}).get("ui", {}).get("visibility", ["model", "app"])

    def open_view(self, tool_name: str) -> dict:
        tool = next(t for t in self.tools if t["name"] == tool_name)
        uri = tool["_meta"]["ui"]["resourceUri"]
        content = self.rpc("resources/read", {"uri": uri})["contents"][0]
        return {"uri": uri, "mimeType": content["mimeType"], "html": content["text"], "csp": csp_for(content.get("_meta", {}).get("ui"))}


def serve_stdio(server: MCPServer) -> None:
    """The stdio transport: newline-delimited JSON-RPC on stdin/stdout, logs on stderr."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            reply = server.handle(json.loads(line))
        except json.JSONDecodeError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    import argparse

    sys.path.insert(0, str(ROOT))
    parser = argparse.ArgumentParser(description="VoltPilot MCP Apps server (stdio)")
    parser.add_argument("--stdio", action="store_true", required=True)
    parser.add_argument("--mode", choices=["static", "declarative", "open_ended", "mixed"], default="mixed")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    from common import registry  # noqa: E402

    module = registry.load("03_mcp_apps", args.mode)
    serve_stdio(module.make_server(live=args.live))
