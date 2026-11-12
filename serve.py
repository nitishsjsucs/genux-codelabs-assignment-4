"""One local server for every lab page.

    python3 serve.py            # http://127.0.0.1:8765  (scripted model, offline)
    python3 serve.py --live     # the same pages, Claude behind them (pip install anthropic)

Routes
    GET  /                             the 6 x 4 lab matrix
    GET  /labs/<tech>/?mode=<mode>     a lab page (auto-plays its scenario)
    GET  /<file>                       static files inside this repository only
    POST /api/<tech>/<mode>[/<sub>]    the lab's handler: SSE when it streams, JSON otherwise

Standard library only; one thread per request so SSE streams do not block each other.
"""

from __future__ import annotations

import argparse
import html
import inspect
import json
import mimetypes
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from common import registry  # noqa: E402
from common.sse import encode  # noqa: E402

LIVE = False
QUIET = False  # tests and the screenshot tool switch the request log off
STATIC_TYPES = {".html", ".js", ".mjs", ".css", ".json", ".png", ".svg", ".txt", ".md"}


def index_page() -> bytes:
    rows = []
    for tech, name, desc in registry.TECHS:
        cells = "".join(
            f'<td><a href="/labs/{tech}/?mode={m}">{registry.MODE_TITLES[m]}</a></td>' for m in registry.MODES
        )
        rows.append(f"<tr><th>{html.escape(name)}<br><small>{html.escape(desc)}</small></th>{cells}</tr>")
    head = "".join(f"<th>{registry.MODE_TITLES[m]}</th>" for m in registry.MODES)
    body = f"""<!doctype html><html><head><meta charset="utf-8"><title>VoltPilot GenUX codelabs</title>
<link rel="stylesheet" href="/common/web/style.css"></head><body><div class="index">
<h1>VoltPilot GenUX codelabs</h1>
<p>Seven technologies x four generation modes. Every page auto-plays a scripted model; add <code>&amp;auto=1</code>
to click the first action automatically, <code>&amp;delay=0</code> to stream instantly.
Model: <b>{'Claude (live)' if LIVE else 'scripted (offline)'}</b>.</p>
<table class="matrix"><tr><th>Technology</th>{head}</tr>{''.join(rows)}</table></div></body></html>"""
    return body.encode()


class Handler(BaseHTTPRequestHandler):
    server_version = "voltpilot/1.0"

    def log_message(self, fmt, *args):  # quieter console: one line per API call
        if not QUIET and "/api/" in (args[0] if args else ""):
            sys.stderr.write("  %s\n" % (fmt % args))

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._send(200, index_page(), "text/html; charset=utf-8")
        target = (ROOT / path.lstrip("/")).resolve()
        if target.is_dir():
            target = target / "index.html"
        if ROOT not in target.parents or target.suffix not in STATIC_TYPES or not target.is_file():
            return self._send(404, b"not found", "text/plain")
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if target.suffix in (".js", ".mjs"):
            ctype = "text/javascript"
        return self._send(200, target.read_bytes(), ctype + ("; charset=utf-8" if ctype.startswith("text") else ""))

    def do_POST(self):
        parts = urlparse(self.path).path.strip("/").split("/")
        if len(parts) < 3 or parts[0] != "api":
            return self._send(404, b"not found", "text/plain")
        tech, mode, sub = parts[1], parts[2], "/".join(parts[3:])
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            delay = float(body.pop("delay", 0) or 0) if isinstance(body, dict) else 0.0
            module = registry.load(tech, mode)
            result = module.http(body, delay=min(delay, 0.5), live=LIVE, sub=sub)
        except KeyError as error:
            return self._send(404, json.dumps({"error": str(error)}).encode(), "application/json")
        except Exception as error:  # noqa: BLE001
            traceback.print_exc()
            return self._send(500, json.dumps({"error": str(error)}).encode(), "application/json")
        if inspect.isgenerator(result) or hasattr(result, "__next__"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                for payload in result:
                    self.wfile.write(encode(payload))
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as error:  # noqa: BLE001 - surface handler errors to the page
                traceback.print_exc()
                self.wfile.write(encode({"type": "SERVER_ERROR", "message": str(error)}))
            self.close_connection = True
            return
        return self._send(200, json.dumps(result).encode(), "application/json")


def make_server(port: int = 8765) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server


def main() -> int:
    global LIVE
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--live", action="store_true", help="use Claude instead of the scripted model")
    args = parser.parse_args()
    LIVE = args.live
    server = make_server(args.port)
    print(f"VoltPilot GenUX codelabs on http://127.0.0.1:{args.port}  (model: {'live Claude' if LIVE else 'scripted'})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
