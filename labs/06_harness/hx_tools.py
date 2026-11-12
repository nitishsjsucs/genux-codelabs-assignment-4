"""The UI tools the harness offers, one family per mode, plus the session store for the web surface."""

from __future__ import annotations

import copy
import json
from collections import OrderedDict
from pathlib import Path

from common import catalog, data, fixtures, labkit, sandbox
from harness import Harness, Tool, WebSurface

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "out" / "artifacts"
S = data.summary()
n = fixtures.node


def obj(props: dict, required: list) -> dict:
    return {"type": "object", "properties": props, "required": required}


# ------------------------------------------------------------------ 1. static: a fixed set of prebuilt components

COMPONENTS = {
    "EnergySummary": (["solar_kwh", "solar_delta_pct", "self_sufficiency_pct", "import_cost"], lambda p: n("Row", [
        n("Metric", label="Solar generated", value=f"{p['solar_kwh']} kWh", delta=f"+{p['solar_delta_pct']}% vs last week", tone="good"),
        n("Metric", label="Self-sufficiency", value=f"{p['self_sufficiency_pct']}%"),
        n("Metric", label="Grid import cost", value=data.money(p["import_cost"]), tone="bad")])),
    "SolarChart": (["days", "solar_kwh"], lambda p: n("Card", [
        n("BarChart", title="Solar generated per day", labels=p["days"], values=p["solar_kwh"], unit="kWh")], title="Solar vs usage")),
    "ChargePlan": (["windows", "recommendation"], lambda p: n("Card", [
        n("Table", columns=["Window", "Source", "Est. cost"], rows=[[w["window"], w["source"], data.money(w["cost"])] for w in p["windows"]]),
        n("Text", text=p["recommendation"])], title="When to charge the EV")),
}


def show_component(args: dict, h: Harness) -> str:
    name, props = args.get("name"), args.get("props") or {}
    if name not in COMPONENTS:
        return f"error: no component {name!r}; available: {sorted(COMPONENTS)}"
    required, build = COMPONENTS[name]
    missing = [k for k in required if k not in props]
    if missing:
        return f"error: {name} needs props {missing}"
    tree = build(props)
    h.ui({"kind": "render", "tree": tree, "component": name, "append": True})
    return f"shown {name}"


SHOW_COMPONENT = Tool("show_component", "Show one of the app's prebuilt components: " + ", ".join(
    f"{k}({', '.join(v[0])})" for k, v in COMPONENTS.items()),
    obj({"name": {"type": "string", "enum": sorted(COMPONENTS)}, "props": {"type": "object"}}, ["name", "props"]), show_component)


# ------------------------------------------------------------------ 2/4. declarative and mixed: render_ui(spec)

def make_render_ui(allow_generated: bool) -> Tool:
    def render_ui(args: dict, h: Harness) -> str:
        spec = args.get("spec")
        errors = catalog.validate_tree(spec, allow_generated=allow_generated)
        if not errors:
            for node in catalog.walk(spec):
                if node["type"] == "GeneratedView":
                    errors += [f"GeneratedView document {p}" for p in sandbox.policy_check(node["props"].get("html", ""))]
        if errors:  # returned to the model, which fixes the spec on its next step
            return "error: spec rejected - " + "; ".join(errors)
        h.state["tree"] = copy.deepcopy(spec)
        h.ui({"kind": "render", "tree": spec})
        return f"rendered {catalog.count(spec)} components on {len(h.surfaces) or 1} surface(s)"

    desc = "Render a component tree {type, props, children} on the user's surfaces. Components:\n" + catalog.describe_for_prompt(allow_generated)
    return Tool("render_ui", desc, obj({"spec": {"type": "object"}}, ["spec"]), render_ui)


# ------------------------------------------------------------------ 3. open-ended: render_html(title, html)

def render_html(args: dict, h: Harness) -> str:
    html, title = args.get("html", ""), args.get("title", "Generated view")
    problems = sandbox.policy_check(html)
    if problems:
        return "error: refused by content policy - the document " + ", ".join(problems)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS / f"{h.id}-{title.lower().replace(' ', '-')}.html"
    path.write_text(html)
    rel = path.relative_to(HERE.parents[1]).as_posix()
    h.ui({"kind": "html", "title": title, "html": html, "bytes": len(html.encode()), "artifact": rel})
    return f"shown {title!r} ({len(html.encode())} bytes) - sandboxed on the web surface, saved as {rel}"


RENDER_HTML = Tool("render_html", "Show a self-contained HTML document (inline CSS/JS, no network) in a sandbox. "
                   "Buttons may call window.voltpilot.action(name, params).",
                   obj({"title": {"type": "string"}, "html": {"type": "string"}}, ["title", "html"]), render_html)


# ------------------------------------------------------------------ the action tool (modes 3 and 4)

def schedule_ev_charge(args: dict, h: Harness) -> str:
    booking = labkit.schedule(args.get("window"))
    if h.state.get("tree"):  # the harness owns the UI state: patch the confirmation in and re-render
        tree = h.state["tree"]
        tree["children"].insert(1, n("Text", text=booking["message"], variant="success"))
        h.ui({"kind": "render", "tree": tree})
    else:
        h.ui({"kind": "notice", "text": booking["message"]})
    return booking["message"]


SCHEDULE = Tool("schedule_ev_charge", "Book the EV charge for an offered window.",
                obj({"window": {"type": "string", "enum": [w["window"] for w in data.CHARGE_WINDOWS]}}, ["window"]),
                schedule_ev_charge)


def system(extra: str) -> str:
    return ("You are VoltPilot, a home-energy copilot running in an agent harness. " + extra +
            " When a message starts with [ui-action], carry out that action with the matching tool. DATA: "
            + json.dumps({"summary": S, "week": data.WEEK, "windows": data.CHARGE_WINDOWS}))


# ------------------------------------------------------------------ web sessions

SESSIONS: "OrderedDict[str, Harness]" = OrderedDict()


def web_run(make_harness, body: dict, sub: str):
    """POST /api/06_harness/<mode>          -> new session, run the prompt, stream events
       POST /api/06_harness/<mode>/action   -> {session, action, params}: inject a click into that session"""
    if sub == "action":
        h = SESSIONS.get(body.get("session", ""))
        if h is None:
            return iter([{"kind": "error", "message": "unknown or expired session"}])
        return h.inject_action(body.get("action"), body.get("params") or {})
    h = make_harness([WebSurface()])
    SESSIONS[h.id] = h
    while len(SESSIONS) > 20:
        SESSIONS.popitem(last=False)

    def stream():
        yield {"kind": "session", "id": h.id}
        yield from h.run(data.PROMPT)
    return stream()
