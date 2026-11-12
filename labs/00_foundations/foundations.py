"""The four generation modes with no protocol at all - the vocabulary every later lab reuses.

One question, one model call, one JSON reply per mode. The only thing that
changes is how much of the interface the model is allowed to decide:

    static       the model names a component the app already has and fills its props
    declarative  the model composes a tree from a catalog of allowed components
    open_ended   the model writes the markup itself (HTML), run in a sandbox
    mixed        a catalog tree with one sandboxed GeneratedView region where the catalog runs out

Labs 01-06 keep these four modes and change the *delivery*: events (AG-UI),
envelope messages (A2UI), an MCP host (MCP Apps), patch streams (json-render),
a compact language (OpenUI Lang), and an agent loop (harness integration).
"""

from __future__ import annotations

import json

from common import catalog, data, fixtures, sandbox, term
from common.llm import collect

S = data.summary()

# What the app owns in static mode: its component, its layout. The model supplies props only.
APP_COMPONENTS = {
    "WeeklySummary": ["solar_kwh", "self_sufficiency_pct", "import_cost", "best_window", "saving_vs_peak"],
}


def weekly_summary(p: dict) -> dict:
    n = fixtures.node
    return n("Card", [
        n("Row", [n("Metric", label="Solar", value=f"{p['solar_kwh']} kWh"),
                  n("Metric", label="Self-sufficiency", value=f"{p['self_sufficiency_pct']}%"),
                  n("Metric", label="Grid import cost", value=data.money(p["import_cost"]))]),
        n("Text", text=f"Charge {p['best_window']} - saves {data.money(p['saving_vs_peak'])} vs peak."),
    ], title="WeeklySummary (an app component)")


SCRIPTS = {
    "static": {"component": "WeeklySummary", "props": {k: S[k] for k in APP_COMPONENTS["WeeklySummary"]}},
    "declarative": fixtures.dashboard_tree(),
    "open_ended": fixtures.energy_clock_html(),
    "mixed": fixtures.dashboard_tree(with_actions=True, with_generated=True),
}

SYSTEMS = {
    "static": "Reply with JSON {component, props}. Components: " + json.dumps(APP_COMPONENTS),
    "declarative": "Reply with one JSON component tree {type, props, children}. Components:\n" + catalog.describe_for_prompt(False),
    "open_ended": "Reply with one self-contained HTML document (inline CSS/JS, no network).",
    "mixed": "Reply with one JSON component tree; you may use one GeneratedView for what the catalog cannot draw:\n" + catalog.describe_for_prompt(True),
}


def model_text(mode: str) -> str:
    v = SCRIPTS[mode]
    return v if isinstance(v, str) else json.dumps(v)


def handle(mode: str, reply: str) -> dict:
    """What the APP does with the model's reply in each mode: the trust decision lives here."""
    if mode == "static":
        msg = json.loads(reply)
        props = APP_COMPONENTS.get(msg.get("component"))
        missing = [k for k in props or [] if k not in msg.get("props", {})]
        errors = ([f"unknown component {msg.get('component')!r}"] if props is None else []) + [f"missing prop {k}" for k in missing]
        tree = weekly_summary(msg["props"]) if not errors else None
        return {"mode": mode, "model_output": msg, "errors": errors, "tree": tree}
    if mode in ("declarative", "mixed"):
        tree = json.loads(reply)
        errors = catalog.validate_tree(tree, allow_generated=(mode == "mixed"))
        return {"mode": mode, "model_output": tree, "errors": errors, "tree": tree if not errors else None}
    problems = sandbox.policy_check(reply)
    return {"mode": mode, "model_output": reply, "errors": problems, "html": reply if not problems else None}


def respond(mode: str, model) -> dict:
    text, _ = collect(model.stream([{"role": "user", "content": data.PROMPT}], system=SYSTEMS[mode]))
    start = text.find("{") if mode != "open_ended" else max(text.lower().find("<!doctype"), 0)
    out = handle(mode, text[start:] if start >= 0 else text)
    out["bytes"] = len(text.encode())
    return out


def print_result(out: dict) -> None:
    mo = out["model_output"]
    shown = mo if isinstance(mo, str) else json.dumps(mo)
    print(f"model output ({out['bytes']} bytes): {shown[:160]}{'...' if len(shown) > 160 else ''}")
    print(f"app checks: {out['errors'] or 'passed'}")
    if out.get("tree"):
        print("app renders (terminal renderer):\n" + term.to_text(out["tree"]))
    if out.get("html"):
        print(f"app renders: sandboxed iframe (srcdoc) with CSP: {sandbox.CSP}")
