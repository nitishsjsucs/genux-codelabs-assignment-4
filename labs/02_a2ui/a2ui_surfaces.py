"""The VoltPilot surfaces in A2UI form, and the server's relay that checks every message.

Who writes what, per mode:

    static       developer: createSurface + updateComponents (TEMPLATE below)
                 model:     updateDataModel only - anything else is refused
    declarative  model:     createSurface + updateComponents + updateDataModel (energy catalog)
    open_ended   model:     a surface on the energy-open catalog whose HtmlFrame holds generated HTML
    mixed        model:     catalog dashboard + HtmlFrame + Buttons; clicks come back as A2UI actions
"""

from __future__ import annotations

import json
from typing import Iterator, List, Optional, Set

import a2ui
from common import data, fixtures, labkit

S = data.summary()
SID = "voltpilot-week"


def t(cid: str, text, variant: Optional[str] = None) -> dict:
    c = {"id": cid, "component": "Text", "text": text}
    if variant:
        c["variant"] = variant
    return c


# --------------------------------------------------------------- 1. static: the developer's template

TEMPLATE = [
    {"id": "root", "component": "Card", "child": "report"},
    {"id": "report", "component": "Column", "children": ["title", "metrics", "chart", "advice"]},
    t("title", "Weekly energy report", "h2"),
    {"id": "metrics", "component": "Row", "children": ["m-solar", "m-self", "m-cost"]},
    {"id": "m-solar", "component": "Metric", "label": "Solar", "value": {"path": "/report/solar"},
     "delta": {"path": "/report/solarDelta"}, "tone": "good"},
    {"id": "m-self", "component": "Metric", "label": "Self-sufficiency", "value": {"path": "/report/selfSufficiency"}},
    {"id": "m-cost", "component": "Metric", "label": "Grid import cost", "value": {"path": "/report/importCost"}, "tone": "bad"},
    {"id": "chart", "component": "BarChart", "title": "Solar per day", "labels": {"path": "/report/days"},
     "values": {"path": "/report/solarByDay"}, "unit": "kWh"},
    t("advice", {"path": "/report/advice"}),
]

STATIC_DATA = [  # the model's whole job in static mode: fill the paths the template binds
    ("/report/solar", f"{S['solar_kwh']} kWh"),
    ("/report/solarDelta", f"+{S['solar_delta_pct']}% vs last week"),
    ("/report/selfSufficiency", f"{S['self_sufficiency_pct']}%"),
    ("/report/importCost", data.money(S["import_cost"])),
    ("/report/days", [d["day"] for d in data.WEEK]),
    ("/report/solarByDay", [d["solar"] for d in data.WEEK]),
    ("/report/advice", fixtures.recommendation_text()),
]


# --------------------------------------------------------------- 2-4. model-written surfaces

def header_and_metrics() -> List[dict]:
    return [
        t("hdr", "Your solar week", "h1"),
        {"id": "metrics", "component": "Row", "children": ["m1", "m2", "m3", "m4"]},
        {"id": "m1", "component": "Metric", "label": "Solar generated", "value": f"{S['solar_kwh']} kWh",
         "delta": f"+{S['solar_delta_pct']}% vs last week", "tone": "good"},
        {"id": "m2", "component": "Metric", "label": "Self-sufficiency", "value": f"{S['self_sufficiency_pct']}%",
         "delta": f"best day {S['best_day']}"},
        {"id": "m3", "component": "Metric", "label": "Grid import cost", "value": data.money(S["import_cost"]),
         "delta": f"{S['import_kwh']} kWh", "tone": "bad"},
        {"id": "m4", "component": "Metric", "label": "Home battery", "value": f"{S['battery_pct']}%"},
    ]


def chart_card() -> List[dict]:
    return [
        {"id": "chart-card", "component": "Card", "child": "chart-col"},
        {"id": "chart-col", "component": "Column", "children": ["chart-title", "chart"]},
        t("chart-title", "Solar vs usage", "h2"),
        {"id": "chart", "component": "BarChart", "title": "Solar generated per day",
         "labels": [d["day"] for d in data.WEEK], "values": [d["solar"] for d in data.WEEK], "unit": "kWh"},
    ]


def ev_card(with_actions: bool) -> List[dict]:
    kids = ["ev-title", "ev-sub", "ev-table", "ev-advice"] + (["ev-actions"] if with_actions else [])
    comps = [
        {"id": "ev-card", "component": "Card", "child": "ev-col"},
        {"id": "ev-col", "component": "Column", "children": kids},
        t("ev-title", "When to charge the EV", "h2"),
        t("ev-sub", f"{S['ev_kwh_needed']} kWh needed - about {S['ev_hours']} h at {data.EV['charger_kw']} kW", "caption"),
        {"id": "ev-table", "component": "Table", "columns": ["Window", "Source", "Est. cost"], "rows": {"path": "/ev/windows"}},
        t("ev-advice", fixtures.recommendation_text()),
    ]
    if with_actions:
        comps += [
            {"id": "ev-actions", "component": "Row", "children": ["btn-schedule", "btn-dismiss"]},
            {"id": "btn-schedule", "component": "Button", "child": "btn-schedule-label", "variant": "primary",
             "action": {"event": {"name": "schedule_ev_charge", "context": {"window": {"path": "/ev/bestWindow"}}}}},
            t("btn-schedule-label", f"Schedule {S['best_window']}"),
            {"id": "btn-dismiss", "component": "Button", "child": "btn-dismiss-label", "variant": "secondary",
             "action": {"event": {"name": "dismiss", "context": {}}}},
            t("btn-dismiss-label", "Not now"),
        ]
    return comps


def clock_card() -> List[dict]:
    return [
        {"id": "clock-card", "component": "Card", "child": "clock-col"},
        {"id": "clock-col", "component": "Column", "children": ["clock-title", "clock-note", "clock"]},
        t("clock-title", "Today on the clock", "h2"),
        t("clock-note", "Not in any catalog: model-written HTML, run by the energy-open catalog's sandboxed HtmlFrame.", "caption"),
        {"id": "clock", "component": "HtmlFrame", "title": "Energy clock", "html": {"path": "/clock/html"}, "height": 280},
    ]


EV_DATA = {"windows": [[w["window"], w["source"], data.money(w["cost"])] for w in data.CHARGE_WINDOWS],
           "bestWindow": S["best_window"]}


def declarative_reply() -> List[dict]:
    return [
        a2ui.create_surface(SID, a2ui.ENERGY_CATALOG),
        a2ui.update_components(SID, [{"id": "root", "component": "Column", "children": ["hdr", "metrics", "chart-card", "ev-card"]}]
                               + header_and_metrics()),
        a2ui.update_components(SID, chart_card()),
        a2ui.update_components(SID, ev_card(with_actions=False)),
        a2ui.update_data_model(SID, "/ev", EV_DATA),
    ]


def open_ended_reply() -> List[dict]:
    return [
        a2ui.create_surface(SID, a2ui.ENERGY_OPEN_CATALOG),
        a2ui.update_components(SID, [{"id": "root", "component": "Column", "children": ["clock-card"]}] + clock_card()),
        a2ui.update_data_model(SID, "/clock/html", fixtures.energy_clock_html()),
    ]


MIXED_ROOT = ["hdr", "metrics", "chart-card", "ev-card", "clock-card"]


def mixed_reply() -> List[dict]:
    return [
        a2ui.create_surface(SID, a2ui.ENERGY_OPEN_CATALOG),
        a2ui.update_components(SID, [{"id": "root", "component": "Column", "children": MIXED_ROOT}] + header_and_metrics()),
        a2ui.update_components(SID, chart_card() + ev_card(with_actions=True)),
        a2ui.update_data_model(SID, "/ev", EV_DATA),
        a2ui.update_components(SID, clock_card()),
        a2ui.update_data_model(SID, "/clock/html", fixtures.energy_clock_html()),
    ]


# where the confirmation Callout goes, per mode: (parent id, its new children)
CALLOUT_PARENT = {
    "mixed": ("root", ["hdr", "booked"] + MIXED_ROOT[1:]),
    "open_ended": ("clock-col", ["clock-title", "booked", "clock-note", "clock"]),
}


def action_reply(name: str, context: dict, mode: str = "mixed") -> List[dict]:
    """The model's answer to a click: one data update, one structural update."""
    parent, children = CALLOUT_PARENT[mode]
    text = "Okay - nothing booked." if name == "dismiss" else labkit.schedule(context.get("window"))["message"]
    return [
        a2ui.update_data_model(SID, "/ev/status", text),
        a2ui.update_components(SID, [
            {"id": parent, "component": "Column", "children": children},
            {"id": "booked", "component": "Callout", "text": {"path": "/ev/status"}, "tone": "good"},
        ]),
    ]


def handle_action(message: dict, model, system: str, surface_messages: List[dict]) -> Iterator[dict]:
    """The server side of a click: check the allow-list, then let the model answer with A2UI messages."""
    action = message.get("action") or {}
    name, context = action.get("name"), action.get("context") or {}
    try:
        labkit.check_action(name, context)
    except (PermissionError, ValueError) as error:
        yield {"from": "app", "error": f"action refused: {error}"}
        return
    client = a2ui.Client()
    for m in surface_messages:  # mirror the surface the page holds, so the relay can check references
        client.apply(m)
    turns = [{"role": "user", "content": data.PROMPT}, {"role": "user", "content": labkit.action_text(name, context)}]
    yield from frames("model", relay(model.stream(turns, system=system), client))


# --------------------------------------------------------------- the server's relay

def relay(pieces: Iterator[tuple], client: a2ui.Client, allowed: Optional[Set[str]] = None) -> Iterator[dict]:
    """Parse the model's JSONL, check each message (shape, catalog, mode policy), forward the good ones.

    `client` mirrors the browser's state, so the server can reject a message that
    refers to a surface that does not exist or uses a component outside its catalog.
    """
    for msg in a2ui.jsonl_messages(pieces):
        if "error" in msg:
            yield msg
            continue
        kind = a2ui.kind_of(msg)
        if allowed is not None and kind not in allowed:
            yield {"error": f"{kind} refused: in this mode the model may only send {sorted(allowed)}"}
            continue
        problems = client.apply(msg)
        if problems:
            yield {"error": "; ".join(problems)}
            continue
        yield msg


def system_prompt(catalog_id: str, extra: str = "") -> str:
    comps = a2ui.CATALOGS[catalog_id]
    lines = [f"- {name}: required {sorted(req)}, optional {sorted(opt)}" for name, (req, opt) in comps.items()]
    return (
        f"You are VoltPilot. Reply ONLY with A2UI {a2ui.VERSION} messages, one JSON object per line (JSONL). "
        f"Surface id: {SID}. Catalog: {catalog_id}. Components are a flat list; refer to children by id "
        "('child' or 'children'); bind values to the data model with {\"path\": \"/x\"}.\n"
        + "\n".join(lines) + f"\n{extra}\nDATA: " + json.dumps({"summary": S, "week": data.WEEK, "windows": data.CHARGE_WINDOWS})
    )


# --------------------------------------------------------------- shared by the four mode files

def frames(source: str, messages: Iterator[dict]) -> Iterator[dict]:
    """Our SSE framing: {"from": "app"|"model", "a2ui": <message>} or {"from": ..., "error": ...}."""
    for m in messages:
        yield {"from": source, **({"error": m["error"]} if "error" in m else {"a2ui": m})}


def print_transcript(stream: Iterator[dict], client: a2ui.Client, root_surface: str = SID) -> List[dict]:
    from common import term

    seen = list(stream)
    for f in seen:
        body = f.get("a2ui") or {"error": f.get("error")}
        print(f"  [{f['from']:<5}] {a2ui.describe(body)}")
    if root_surface in client.surfaces:
        s = client.surfaces[root_surface]
        print(f"\nclient state: {len(s.components)} components, data paths {sorted(s.data)}; missing refs: {client.missing_refs(root_surface) or 'none'}")
        print(term.to_text(client.to_tree(root_surface)))
    return seen
