"""Screenshot every lab page with headless Chrome -> docs/screenshots/<tech>-<mode>.png

    python3 tools/screenshots.py                 # all 28 pages
    python3 tools/screenshots.py 01_ag_ui        # one technology

Starts serve.py's server in-process on a spare port, loads each page with
?delay=0 (stream instantly) and, for the open-ended and mixed modes, &auto=1
(the page clicks its first action itself, so the screenshot shows the round
trip), and lets Chrome run the page for a few seconds of virtual time.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import serve  # noqa: E402
from common import registry  # noqa: E402

CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
OUT = ROOT / "docs" / "screenshots"
PORT = 8799


def shoot(url: str, path: Path, height: int = 1100) -> bool:
    # Site isolation is off so sandboxed (opaque-origin) frames stay in-process: with frames in other
    # processes, headless virtual time stalls the host<->view postMessage exchange of the MCP Apps lab.
    cmd = [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
           "--disable-site-isolation-trials", "--disable-features=IsolateOrigins,site-per-process",
           "--no-default-browser-check", f"--window-size=1280,{height}", "--virtual-time-budget=9000",
           f"--screenshot={path}", url]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    return result.returncode == 0 and path.exists()


def main(argv) -> int:
    only = set(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    serve.QUIET = True
    server = serve.make_server(PORT)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    ok = failed = 0
    try:
        for tech, _name, mode in registry.all_labs():
            if only and tech not in only:
                continue
            auto = "&auto=1" if mode in ("open_ended", "mixed") else ""
            url = f"http://127.0.0.1:{PORT}/labs/{tech}/?mode={mode}&delay=0{auto}"
            path = OUT / f"{tech}-{mode}.png"
            if path.exists():
                path.unlink()
            good = shoot(url, path, height=1500 if mode == "mixed" else 1100)
            ok += good
            failed += not good
            print(f"{'ok  ' if good else 'FAIL'} {path.relative_to(ROOT)}  <- {url}")
        if not only:
            good = shoot(f"http://127.0.0.1:{PORT}/", OUT / "index.png", height=760)
            print(f"{'ok  ' if good else 'FAIL'} docs/screenshots/index.png")
    finally:
        server.shutdown()
    print(f"{ok} screenshots, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
