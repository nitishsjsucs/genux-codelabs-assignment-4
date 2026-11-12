"""Foundations · MIXED - a catalog tree with one sandboxed GeneratedView.

No transport protocol: one model call, one JSON reply (POST /api/00_foundations/mixed).
See foundations.py for what the app checks before it draws anything.

Run:  python3 labs/00_foundations/mixed.py [--live]
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

MODE = "mixed"
SCRIPT = [{"text": fd.model_text(MODE)}]


def http(body: dict, delay: float = 0.0, live: bool = False, sub: str = ""):
    return fd.respond(MODE, get_model(SCRIPT, live, delay))


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    print(banner("Foundations · MIXED - a catalog tree with one sandboxed GeneratedView"))
    print(f"user: {data.PROMPT}\n")
    fd.print_result(fd.respond(MODE, get_model(SCRIPT, wants_live(argv))))
    print("\nwhat each mode lets the model decide, and what it costs in output size:")
    print(f"  {'mode':<12} {'bytes':>6}  model decides            app guarantees")
    rows = {"static": ("which component + props", "layout, look, behaviour"),
            "declarative": ("layout from the catalog", "every component is known"),
            "open_ended": ("everything (markup + JS)", "only the sandbox + policy"),
            "mixed": ("layout + one free region", "catalog outside the region")}
    for mode, (decides, keeps) in rows.items():
        out = fd.respond(mode, get_model([{"text": fd.model_text(mode)}]))
        print(f"  {mode:<12} {out['bytes']:>6}  {decides:<24} {keeps}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
