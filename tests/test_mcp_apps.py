import json
import re
import subprocess
import sys
import unittest

from helpers import ROOT, lab, sibling

mcp = sibling("03_mcp_apps", "mcp_server")


def rpc(server, method, params=None, mid=1):
    return server.handle({"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}})


class ServerTest(unittest.TestCase):
    def test_handshake_and_listing(self):
        server = lab("03_mcp_apps", "static").make_server()
        init = rpc(server, "initialize", {"capabilities": {"extensions": {mcp.UI_EXTENSION: {"mimeTypes": [mcp.APP_MIME]}}}})["result"]
        self.assertEqual(init["protocolVersion"], mcp.PROTOCOL_VERSION)
        self.assertIn(mcp.UI_EXTENSION, init["capabilities"]["extensions"])
        self.assertIsNone(server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        tools = {t["name"]: t for t in rpc(server, "tools/list")["result"]["tools"]}
        self.assertEqual(tools["show_energy_dashboard"]["_meta"]["ui"]["resourceUri"], "ui://voltpilot/static-dashboard.html")
        self.assertEqual(tools["schedule_ev_charge"]["_meta"]["ui"]["visibility"], ["app"])

    def test_resource_is_an_app(self):
        for mode in ("static", "declarative", "open_ended", "mixed"):
            server = lab("03_mcp_apps", mode).make_server()
            for res in rpc(server, "resources/list")["result"]["resources"]:
                content = rpc(server, "resources/read", {"uri": res["uri"]})["result"]["contents"][0]
                self.assertEqual(content["mimeType"], "text/html;profile=mcp-app")
                scripts = re.findall(r"<script>(.*?)</script>", content["text"], re.S)
                self.assertEqual(len(scripts), 1, f"{mode}: the inlined bundle must be one intact script")
                self.assertIn("appBridge", scripts[0])

    def test_errors(self):
        server = lab("03_mcp_apps", "static").make_server()
        self.assertEqual(rpc(server, "nope")["error"]["code"], -32601)
        self.assertEqual(rpc(server, "tools/call", {"name": "missing"})["error"]["code"], -32602)
        self.assertEqual(server.handle({"id": 1})["error"]["code"], -32600)
        bad = rpc(server, "tools/call", {"name": "schedule_ev_charge", "arguments": {"window": "x"}})["result"]
        self.assertTrue(bad["isError"])

    def test_generated_specs_and_html(self):
        spec = rpc(lab("03_mcp_apps", "mixed").make_server(), "tools/call", {"name": "render_energy_ui", "arguments": {"question": "q"}})["result"]
        self.assertIn("GeneratedView", spec["content"][0]["text"])
        html = rpc(lab("03_mcp_apps", "open_ended").make_server(), "tools/call", {"name": "generate_energy_view", "arguments": {"question": "q"}})["result"]
        self.assertGreater(html["structuredContent"]["bytes"], 1000)

    def test_csp(self):
        self.assertIn("connect-src 'none'", mcp.csp_for({}))
        csp = mcp.csp_for({"csp": {"connectDomains": ["https://api.example", "https://a; script-src *"]}})
        self.assertIn("connect-src 'self' https://api.example".replace("'self' ", ""), csp)
        self.assertNotIn("script-src *", csp)

    def test_host_visibility(self):
        host = mcp.InProcessHost(lab("03_mcp_apps", "static").make_server(), log=lambda *_: None)
        host.connect()
        self.assertTrue(host.view_may_call("schedule_ev_charge"))
        self.assertFalse(host.model_may_call("schedule_ev_charge"))
        self.assertTrue(host.model_may_call("show_energy_dashboard"))

    def test_stdio_transport(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "render_energy_ui", "arguments": {"question": "q"}}},
        ]
        proc = subprocess.run([sys.executable, str(ROOT / "labs/03_mcp_apps/mcp_server.py"), "--stdio", "--mode", "mixed"],
                              input="\n".join(json.dumps(x) for x in lines) + "\n", capture_output=True, text=True, timeout=60)
        replies = [json.loads(line) for line in proc.stdout.splitlines()]
        self.assertEqual([r["id"] for r in replies], [1, 2, 3])
        self.assertEqual(replies[1]["result"]["tools"][0]["name"], "render_energy_ui")
        self.assertIn("spec", replies[2]["result"]["structuredContent"])


if __name__ == "__main__":
    unittest.main()
