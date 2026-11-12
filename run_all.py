"""Run every lab demo offline and save its transcript to docs/outputs/<tech>-<mode>.txt.

    python3 run_all.py            # all 28 demos (7 technologies x 4 modes)
    python3 run_all.py 03_mcp_apps

Each demo runs in its own process with the scripted model - no network, no key.
Exit status is non-zero if any demo fails.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from common import registry  # noqa: E402

OUT = ROOT / "docs" / "outputs"


def main(argv) -> int:
    only = set(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    rows, failed = [], 0
    for tech, name, mode in registry.all_labs():
        if only and tech not in only:
            continue
        script = ROOT / "labs" / tech / f"{mode}.py"
        start = time.perf_counter()
        proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, cwd=str(ROOT), timeout=180)
        took = time.perf_counter() - start
        text = f"$ python3 labs/{tech}/{mode}.py\n\n{proc.stdout}"
        if proc.returncode:
            text += f"\n[exit {proc.returncode}]\n{proc.stderr}"
            failed += 1
        (OUT / f"{tech}-{mode}.txt").write_text(text)
        lines = proc.stdout.count("\n")
        rows.append((f"{tech}/{mode}", "PASS" if proc.returncode == 0 else "FAIL", lines, took))
        print(f"{'PASS' if proc.returncode == 0 else 'FAIL'}  {tech}/{mode:<12} {lines:>4} lines  {took:5.2f}s  -> docs/outputs/{tech}-{mode}.txt")
    print(f"\n{len(rows) - failed}/{len(rows)} demos passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
