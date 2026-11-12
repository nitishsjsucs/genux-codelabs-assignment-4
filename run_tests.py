"""Every offline check in one command: Python unittest (protocols, modes, server, all 28 demos) + node --test.

    python3 run_tests.py
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    print("== Python: python3 -m unittest discover -s tests")
    py = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=str(ROOT), capture_output=True, text=True)
    tail = py.stderr.strip().splitlines()[-3:]
    print("\n".join(tail))
    ran = re.search(r"Ran (\d+) tests", py.stderr)
    ok_py = py.returncode == 0
    if not ok_py:
        print(py.stderr[-3000:])

    ok_js, js_pass = True, "skipped (node not found)"
    if shutil.which("node"):
        files = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "tests" / "js").glob("*.test.mjs"))
        print("\n== JavaScript: node --test " + " ".join(files))
        js = subprocess.run(["node", "--test", *files], cwd=str(ROOT), capture_output=True, text=True)
        counts = dict(re.findall(r"^# (tests|pass|fail) (\d+)$", js.stdout, re.M))
        js_pass = f"{counts.get('pass', '?')}/{counts.get('tests', '?')} passed"
        print(js_pass)
        ok_js = js.returncode == 0
        if not ok_js:
            print(js.stdout[-3000:])

    print(f"\nsummary: python {'OK' if ok_py else 'FAILED'} ({ran.group(1) if ran else '?'} tests) · javascript {js_pass}")
    return 0 if ok_py and ok_js else 1


if __name__ == "__main__":
    sys.exit(main())
