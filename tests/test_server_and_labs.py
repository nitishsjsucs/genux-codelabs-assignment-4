"""End to end: the HTTP server, and every lab's CLI demo exits 0 offline."""

import json
import subprocess
import sys
import threading
import unittest
import urllib.error
import urllib.request

from helpers import ROOT

import serve
from common import registry


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        serve.QUIET = True
        cls.server = serve.make_server(0)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def get(self, path):
        return urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=30)

    def post(self, path, body):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        return urllib.request.urlopen(req, timeout=60)

    def test_index_lists_every_lab(self):
        html = self.get("/").read().decode()
        for tech, _name, mode in registry.all_labs():
            self.assertIn(f"/labs/{tech}/?mode={mode}", html)

    def test_static_files_stay_inside_the_repo(self):
        self.assertEqual(self.get("/common/web/catalog.js").status, 200)
        for path in ("/../../etc/passwd", "/serve.py", "/.git/config"):
            with self.assertRaises(urllib.error.HTTPError):
                self.get(path)

    def test_every_streaming_lab_answers(self):
        for tech, _name, mode in registry.all_labs():
            if tech == "03_mcp_apps":
                reply = json.loads(self.post(f"/api/{tech}/{mode}", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).read())
                self.assertIn("tools", reply["result"])
                continue
            body = {"messages": [{"id": "u", "role": "user", "content": "q"}], "threadId": "t", "runId": "r",
                    "state": {}, "tools": [], "forwardedProps": {}} if tech == "01_ag_ui" else {}
            res = self.post(f"/api/{tech}/{mode}", body)
            raw = res.read().decode()
            if res.headers.get("Content-Type", "").startswith("text/event-stream"):
                frames = [json.loads(line[5:]) for line in raw.splitlines() if line.startswith("data:")]
                self.assertGreater(len(frames), 1, f"{tech}/{mode}")
                self.assertFalse(any(f.get("type") == "SERVER_ERROR" for f in frames), f"{tech}/{mode}")
            else:
                self.assertIn("mode", json.loads(raw))

    def test_unknown_lab(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post("/api/99_nope/static", {})
        self.assertEqual(ctx.exception.code, 404)


class DemosTest(unittest.TestCase):
    def test_every_demo_runs_offline(self):
        for tech, _name, mode in registry.all_labs():
            with self.subTest(lab=f"{tech}/{mode}"):
                proc = subprocess.run([sys.executable, str(ROOT / "labs" / tech / f"{mode}.py")], capture_output=True,
                                      text=True, timeout=120, cwd=str(ROOT))
                self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
                self.assertNotIn("Traceback", proc.stdout)


if __name__ == "__main__":
    unittest.main()
