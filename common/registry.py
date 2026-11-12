"""Where every lab lives, and how to load one by (technology, mode).

Lab folders start with a number (01_ag_ui), so they are not importable
packages; each mode file is loaded from its path under a unique module name.
The lab folder goes on sys.path so a mode file can import its siblings
(agui.py, a2ui.py, ...), which all have distinct names.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MODES = ["static", "declarative", "open_ended", "mixed"]
MODE_TITLES = {"static": "1 · Static", "declarative": "2 · Declarative", "open_ended": "3 · Open-ended", "mixed": "4 · Mixed"}

TECHS = [
    ("00_foundations", "Foundations", "The four generation modes with no protocol at all"),
    ("01_ag_ui", "AG-UI", "Agent-User Interaction protocol: typed events + shared state over SSE"),
    ("02_a2ui", "A2UI", "Google's declarative UI messages: surfaces, components, data model"),
    ("03_mcp_apps", "MCP Apps", "UI resources (ui://) mounted by an MCP host, JSON-RPC over postMessage"),
    ("04_json_render", "json-render", "A catalog-constrained element map streamed as JSON Patch"),
    ("05_openui", "OpenUI Lang", "A compact line-oriented UI language with forward references"),
    ("06_harness", "Harness integration", "UI tools inside an agent loop, two surfaces"),
]

_cache: dict = {}


def lab_dir(tech: str) -> Path:
    return ROOT / "labs" / tech


def load(tech: str, mode: str):
    key = (tech, mode)
    if key in _cache:
        return _cache[key]
    if tech not in {t for t, _n, _d in TECHS} or mode not in MODES:
        raise KeyError(f"no lab {tech}/{mode}")
    path = lab_dir(tech) / f"{mode}.py"
    for p in (str(ROOT), str(lab_dir(tech))):
        if p not in sys.path:
            sys.path.insert(0, p)
    spec = importlib.util.spec_from_file_location(f"lab_{tech}_{mode}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _cache[key] = module
    return module


def all_labs():
    for tech, name, _desc in TECHS:
        for mode in MODES:
            yield tech, name, mode
