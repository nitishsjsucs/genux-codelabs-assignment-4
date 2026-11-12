"""What the scripted model "writes" - one dashboard, many encodings.

Every declarative lab's scripted reply is this canonical tree serialized into
that lab's wire format (an AG-UI state, A2UI messages, json-render patches, an
OpenUI Lang program...). The transcripts in docs/outputs show the literal text
the model streamed. Building them from one tree guarantees that every lab shows
the same numbers, so the comparison between technologies is fair.

With --live, Claude writes these replies instead; the scripts below are the
answers a well-behaved model is expected to give.
"""

from __future__ import annotations

from pathlib import Path

from common import data

S = data.summary()
HERE = Path(__file__).resolve().parent


def node(kind: str, children=None, **props) -> dict:
    return {"type": kind, "props": {k: v for k, v in props.items() if v is not None}, "children": children or []}


def energy_clock_html() -> str:
    """The open-ended artifact: a 24-hour radial chart no catalog component can draw."""
    return (HERE / "fixtures" / "energy_clock.html").read_text()


def metrics_row() -> dict:
    return node("Row", [
        node("Metric", label="Solar generated", value=f"{S['solar_kwh']} kWh", delta=f"+{S['solar_delta_pct']}% vs last week", tone="good"),
        node("Metric", label="Self-sufficiency", value=f"{S['self_sufficiency_pct']}%", delta=f"best day {S['best_day']}"),
        node("Metric", label="Grid import cost", value=data.money(S["import_cost"]), delta=f"{S['import_kwh']} kWh", tone="bad"),
        node("Metric", label="Home battery", value=f"{S['battery_pct']}%"),
    ], gap="medium")


def solar_chart() -> dict:
    return node("BarChart", title="Solar generated per day", labels=[d["day"] for d in data.WEEK],
                values=[d["solar"] for d in data.WEEK], unit="kWh")


def windows_table() -> dict:
    return node("Table", columns=["Window", "Source", "Est. cost"],
                rows=[[w["window"], w["source"], data.money(w["cost"])] for w in data.CHARGE_WINDOWS])


def recommendation_text() -> str:
    return f"Charge {S['best_window']} on solar surplus - saves {data.money(S['saving_vs_peak'])} vs peak."


def action_buttons() -> dict:
    return node("Row", [
        node("Button", label=f"Schedule {S['best_window']}", action="schedule_ev_charge",
             params={"window": S["best_window"]}, variant="primary"),
        node("Button", label="Not now", action="dismiss", variant="secondary"),
    ], gap="small")


def dashboard_tree(with_actions: bool = False, with_generated: bool = False) -> dict:
    ev_children = [windows_table(), node("Text", text=recommendation_text(), variant="body")]
    if with_actions:
        ev_children.append(action_buttons())
    children = [
        node("Text", text="Your solar week", variant="h1"),
        metrics_row(),
        node("Card", [solar_chart()], title="Solar vs usage"),
        node("Card", ev_children, title="When to charge the EV",
             subtitle=f"{S['ev_kwh_needed']} kWh needed - about {S['ev_hours']} h at {data.EV['charger_kw']} kW"),
    ]
    if with_generated:
        children.append(node("Card", [
            node("GeneratedView", title="Energy clock", html=energy_clock_html(), height=280),
        ], title="Today on the clock", subtitle="A view the catalog cannot draw - generated, sandboxed"))
    return node("Column", children, gap="medium")


def assign_ids(tree: dict) -> dict:
    """Give every node a stable, readable id (metric-1, card-2 ...) - flat formats need them."""
    counters: dict = {}
    first = [True]

    def visit(n: dict) -> dict:
        out = dict(n)
        if n.get("id"):
            out["id"] = n["id"]
        elif first[0]:
            out["id"] = "root"
        else:
            kind = n["type"].lower()
            counters[kind] = counters.get(kind, 0) + 1
            out["id"] = f"{kind}-{counters[kind]}"
        first[0] = False
        out["children"] = [visit(c) for c in n.get("children") or []]
        return out

    return visit(tree)


def to_flat(tree: dict) -> dict:
    """Canonical tree -> {root, elements} (json-render's shape, AG-UI's state shape here)."""
    tree = assign_ids(tree)
    elements: dict = {}

    def visit(n: dict):
        elements[n["id"]] = {"type": n["type"], "props": n["props"], "children": [c["id"] for c in n["children"]]}
        for c in n["children"]:
            visit(c)

    visit(tree)
    return {"root": tree["id"], "elements": elements}


CONFIRMATION = f"Booked: the EV will charge {S['best_window']} (estimated {data.money(S['best_cost'])})."
