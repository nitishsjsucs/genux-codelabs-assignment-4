"""A second renderer for the same canonical tree: plain text for a terminal.

The web renderer (common/web/catalog.js) and this one read the same spec. That
is the "one spec, two renderers" idea from json-render and from the harness
lab: the model describes *what* to show; each surface decides *how*.
"""

from __future__ import annotations

from typing import List

WIDTH = 74


def _leaf(node: dict) -> str:
    p = node.get("props") or {}
    kind = node.get("type")
    if kind == "Metric":
        delta = f" ({p['delta']})" if p.get("delta") else ""
        return f"{p.get('label')}: {p.get('value')}{delta}"
    if kind == "Text":
        text = str(p.get("text", ""))
        return text.upper() if p.get("variant") == "h1" else text
    if kind == "Button":
        return f"[ {p.get('label')} ] -> {p.get('action')}"
    if kind == "__pending":
        return f"[waiting for {p.get('ref')}]"
    return kind or "?"


def render(node: dict, indent: int = 0) -> List[str]:
    pad = " " * indent
    kind = node.get("type")
    p = node.get("props") or {}
    kids = node.get("children") or []
    if kind == "Column":
        lines: List[str] = []
        for child in kids:
            lines.extend(render(child, indent))
        return lines
    if kind == "Row":
        if all(c.get("type") in ("Metric", "Text", "Button") for c in kids):
            return [pad + "  |  ".join(_leaf(c) for c in kids)]
        lines = []
        for child in kids:
            lines.extend(render(child, indent))
        return lines
    if kind == "Card":
        title = p.get("title", "")
        sub = f" - {p['subtitle']}" if p.get("subtitle") else ""
        head = f"{pad}+-- {title}{sub} " if title else f"{pad}+"
        lines = [head + "-" * max(2, WIDTH - len(head))]
        for child in kids:
            lines.extend(render(child, indent + 2))
        lines.append(pad + "+" + "-" * (WIDTH - indent - 1))
        return lines
    if kind == "BarChart":
        values = p.get("values") or []
        top = max(values) if values else 1
        unit = f" {p['unit']}" if p.get("unit") else ""
        lines = [pad + str(p.get("title", ""))]
        for label, value in zip(p.get("labels") or [], values):
            bar = "#" * int(round(30 * value / top)) if top else ""
            lines.append(f"{pad}  {label:>4} {bar:<30} {value}{unit}")
        return lines
    if kind == "Table":
        cols = p.get("columns") or []
        rows = [[str(c) for c in r] for r in p.get("rows") or []]
        widths = [max([len(str(c))] + [len(r[i]) for r in rows if i < len(r)]) for i, c in enumerate(cols)]
        fmt = "  ".join("{:<%d}" % w for w in widths)
        lines = [pad + fmt.format(*cols), pad + "  ".join("-" * w for w in widths)]
        lines += [(pad + fmt.format(*(r + [""] * (len(cols) - len(r))))).rstrip() for r in rows]
        return lines
    if kind == "GeneratedView":
        size = len(str(p.get("html", "")).encode())
        return [f"{pad}[generated view: {p.get('title')} - {size} bytes of HTML; open the web surface to see it]"]
    return [pad + _leaf(node)]


def to_text(node: dict) -> str:
    return "\n".join(render(node))
