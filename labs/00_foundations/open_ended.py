"""Foundations · OPEN-ENDED - the model writes HTML; the app sandboxes it.

No transport protocol: one model call, one JSON reply (POST /api/00_foundations/open_ended).
See foundations.py for what the app checks before it draws anything.

Run:  python3 labs/00_foundations/open_ended.py [--live]
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import foundations as fd  # noqa: E402
from common import data  # noqa: E402
from common.llm import get_model, wants_live  # noqa: E402
from common.sse import banner  # noqa: E402

MODE = "open_ended"
SCRIPT = [{"text": fd.model_text(MODE)}]


def http(body: dict, delay: float = 0.0, live: bool = False, sub: str = ""):
    return fd.respond(MODE, get_model(SCRIPT, live, delay))


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    print(banner("Foundations · OPEN-ENDED - the model writes HTML; the app sandboxes it"))
    print(f"user: {data.PROMPT}\n")
    fd.print_result(fd.respond(MODE, get_model(SCRIPT, wants_live(argv))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
