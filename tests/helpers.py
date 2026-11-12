"""Test helpers: repo root on sys.path, and the lab loader."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common import registry  # noqa: E402
from common.llm import ScriptedModel  # noqa: E402


def lab(tech: str, mode: str):
    return registry.load(tech, mode)


def sibling(tech: str, name: str):
    """Import a lab's sibling module (agui, a2ui, ...) - registry.load put its folder on sys.path."""
    registry.load(tech, "static")
    __import__(name)
    return sys.modules[name]


def scripted(turns):
    return ScriptedModel(turns)
