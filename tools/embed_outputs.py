"""Copy real captured output (docs/outputs/*.txt, written by run_all.py) into the READMEs.

A README marks a slot with an HTML comment followed by a fenced block:

    <!-- output: 01_ag_ui-static from="RUN 2" n=8 -->
    ```text
    (replaced)
    ```

    from="..."  start at the first line containing this text (default: the first line)
    n=K         take K lines (default 20)

so every excerpt in the docs is the program's actual output, refreshed by
`python3 run_all.py && python3 tools/embed_outputs.py`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARK = re.compile(r'<!-- output: (?P<file>[\w.-]+)(?: from="(?P<frm>[^"]*)")?(?: n=(?P<n>\d+))? -->\n```text\n.*?\n```', re.S)


def excerpt(file: str, frm: str, n: int) -> str:
    lines = (ROOT / "docs" / "outputs" / f"{file}.txt").read_text().splitlines()
    start = 0
    if frm:
        start = next((i for i, line in enumerate(lines) if frm in line), None)
        if start is None:
            raise SystemExit(f"{file}: no line contains {frm!r}")
    chunk = [line.rstrip() for line in lines[start:start + n]]
    return "\n".join(chunk)


def main() -> int:
    readmes = [ROOT / "README.md", *sorted((ROOT / "labs").glob("*/README.md"))]
    total = 0
    for path in readmes:
        if not path.exists():
            continue
        text = path.read_text()

        def fill(m):
            body = excerpt(m["file"], m["frm"] or "", int(m["n"] or 20))
            return m.group(0).split("\n", 1)[0] + "\n```text\n" + body + "\n```"

        new, count = MARK.subn(fill, text)
        total += count
        if new != text:
            path.write_text(new)
        print(f"{path.relative_to(ROOT)}: {count} excerpt(s)")
    print(f"{total} excerpts embedded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
