"""OpenUI Lang, written from scratch: tokenizer, parser, resolver, streaming, serializer.

An OpenUI Lang program is one statement per line:

    root = Stack([title, kpis], "column", "m")
    title = Text("Your solar week", "h1")
    kpis = Stack([solar, cost], "row", "m")
    solar = Metric("Solar", "133.3 kWh", "+9%")

Components take POSITIONAL arguments (the catalog fixes their order), values
are JSON-like (strings, numbers, true/false/null, [arrays], {objects}), and a
bare lowercase name is a reference to another statement. `root` may be written
first and refer to names defined later - forward references are what make the
format stream well: the page draws the skeleton from line 1 and fills each
placeholder when its line arrives. A later statement with the same name
replaces the earlier one, which is how a follow-up edits a program.
"""

from __future__ import annotations

import json
import re
from typing import Dict, List, Optional, Tuple

# Component -> positional parameter names (and how the canonical renderer names it).
SIGNATURES: Dict[str, List[str]] = {
    "Stack": ["children", "direction", "gap"],
    "Card": ["title", "children", "subtitle"],
    "Text": ["text", "variant"],
    "Metric": ["label", "value", "delta", "tone"],
    "BarChart": ["title", "labels", "values", "unit"],
    "Table": ["columns", "rows"],
    "Button": ["label", "action", "variant", "params"],
    "HtmlArtifact": ["title", "document", "height"],
}
GAPS = {"s": "small", "m": "medium", "l": "large"}

TOKEN = re.compile(r"""
    (?P<ws>\s+)
  | (?P<string>"(?:[^"\\]|\\.)*")
  | (?P<number>-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)
  | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<punct>[=()\[\]{},:])
""", re.X)


class OpenUIError(ValueError):
    pass


def tokenize(line: str) -> List[Tuple[str, str]]:
    pos, out = 0, []
    while pos < len(line):
        m = TOKEN.match(line, pos)
        if not m:
            raise OpenUIError(f"unexpected character {line[pos]!r} at column {pos + 1}")
        pos = m.end()
        if m.lastgroup != "ws":
            out.append((m.lastgroup, m.group()))
    return out


class _Parser:
    def __init__(self, tokens):
        self.t, self.i = tokens, 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else ("eof", "")

    def take(self, value=None):
        tok = self.peek()
        if value is not None and tok[1] != value:
            raise OpenUIError(f"expected {value!r}, found {tok[1] or 'end of line'!r}")
        self.i += 1
        return tok

    def expr(self):
        kind, value = self.peek()
        if kind == "string":
            self.take()
            return ("lit", json.loads(value))
        if kind == "number":
            self.take()
            return ("lit", float(value) if any(c in value for c in ".eE") else int(value))
        if value == "[":
            self.take("[")
            items = self.items("]")
            return ("arr", items)
        if value == "{":
            self.take("{")
            pairs = []
            while self.peek()[1] != "}":
                k_kind, key = self.take()
                key = json.loads(key) if k_kind == "string" else key
                self.take(":")
                pairs.append((key, self.expr()))
                if self.peek()[1] == ",":
                    self.take(",")
            self.take("}")
            return ("obj", pairs)
        if kind == "name":
            self.take()
            if value in ("true", "false", "null"):
                return ("lit", {"true": True, "false": False, "null": None}[value])
            if self.peek()[1] == "(":
                self.take("(")
                return ("call", value, self.items(")"))
            return ("ref", value)
        raise OpenUIError(f"unexpected {value or 'end of line'!r}")

    def items(self, close):
        items = []
        while self.peek()[1] != close:
            items.append(self.expr())
            if self.peek()[1] == ",":
                self.take(",")
            elif self.peek()[1] != close:
                raise OpenUIError(f"expected ',' or {close!r}, found {self.peek()[1] or 'end of line'!r}")
        self.take(close)
        return items


def parse_statement(line: str) -> Tuple[str, tuple]:
    p = _Parser(tokenize(line))
    kind, name = p.take()
    if kind != "name":
        raise OpenUIError(f"a statement starts with a name, found {name!r}")
    p.take("=")
    value = p.expr()
    if p.peek()[0] != "eof":
        raise OpenUIError(f"trailing {p.peek()[1]!r}")
    return name, value


class Program:
    """A program that grows line by line (feed) and resolves on demand (tree)."""

    def __init__(self):
        self.statements: Dict[str, tuple] = {}
        self.order: List[str] = []
        self.errors: List[str] = []
        self._buffer = ""
        self.lines = 0

    def feed(self, text: str) -> List[str]:
        """Add streamed text; returns the names of statements completed by it."""
        self._buffer += text
        done = []
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            name = self._line(line)
            if name:
                done.append(name)
        return done

    def close(self) -> List[str]:
        name = self._line(self._buffer)
        self._buffer = ""
        return [name] if name else []

    def _line(self, line: str) -> Optional[str]:
        line = line.strip()
        if not line or line.startswith(("#", "//", "```")):
            return None
        self.lines += 1
        try:
            name, value = parse_statement(line)
        except OpenUIError as error:
            self.errors.append(f"line {self.lines}: {error}")
            return None
        if name not in self.statements:
            self.order.append(name)
        self.statements[name] = value
        return name

    def pending(self, root: str = "root") -> List[str]:
        """Names reachable from root that are not defined yet (still streaming, or missing)."""
        missing, seen = [], set()

        def walk(e):
            if e[0] == "ref":
                if e[1] in self.statements:
                    if e[1] not in seen:
                        seen.add(e[1])
                        walk(self.statements[e[1]])
                elif e[1] not in missing:
                    missing.append(e[1])
            elif e[0] in ("arr",):
                for x in e[1]:
                    walk(x)
            elif e[0] == "obj":
                for _k, x in e[1]:
                    walk(x)
            elif e[0] == "call":
                for x in e[2]:
                    walk(x)

        walk(("ref", root))
        return missing

    def tree(self, root: str = "root") -> dict:
        """The program as a canonical tree; undefined references become __pending placeholders."""
        return to_canonical(self._value(("ref", root), set()))

    def _value(self, e, stack):
        kind = e[0]
        if kind == "lit":
            return e[1]
        if kind == "arr":
            return [self._value(x, stack) for x in e[1]]
        if kind == "obj":
            return {k: self._value(x, stack) for k, x in e[1]}
        if kind == "ref":
            name = e[1]
            if name not in self.statements:
                return {"__component": "__pending", "ref": name}
            if name in stack:
                raise OpenUIError(f"reference cycle through {name}")
            return self._value(self.statements[name], stack | {name})
        if kind == "call":
            comp, args = e[1], e[2]
            if comp not in SIGNATURES:
                return {"__component": "__unknown", "name": comp}
            params = SIGNATURES[comp]
            if len(args) > len(params):
                raise OpenUIError(f"{comp} takes at most {len(params)} arguments, got {len(args)}")
            values = {params[i]: self._value(a, stack) for i, a in enumerate(args)}
            return {"__component": comp, **values}
        raise OpenUIError(f"bad expression {e!r}")


def to_canonical(v) -> dict:
    """Resolved OpenUI values -> canonical node (common/catalog.py)."""
    if not isinstance(v, dict) or "__component" not in v:
        return {"type": "Text", "props": {"text": str(v)}, "children": []}
    comp = v["__component"]
    kids = [to_canonical(c) for c in v.get("children") or []] if isinstance(v.get("children"), list) else []
    if comp == "__pending":
        return {"type": "__pending", "props": {"ref": v["ref"]}, "children": []}
    if comp == "__unknown":
        return {"type": v["name"], "props": {}, "children": []}  # the validator reports it
    if comp == "Stack":
        kind = "Row" if v.get("direction") == "row" else "Column"
        return {"type": kind, "props": {"gap": GAPS.get(v.get("gap"), "medium")}, "children": kids}
    if comp == "HtmlArtifact":
        return {"type": "GeneratedView", "props": {"title": v.get("title", ""), "html": v.get("document", ""),
                                                   "height": v.get("height") or 260}, "children": []}
    props = {k: val for k, val in v.items() if k not in ("__component", "children") and val is not None}
    if comp == "Button":
        props.setdefault("params", {})
    return {"type": comp, "props": props, "children": kids}


# --------------------------------------------------------------------- canonical tree -> program

def lit(v) -> str:
    if isinstance(v, dict):
        return "{" + ", ".join(f"{k}: {lit(x)}" for k, x in v.items()) + "}"
    if isinstance(v, list):
        return "[" + ", ".join(lit(x) for x in v) + "]"
    return json.dumps(v)


def from_tree(tree: dict, names: Optional[Dict[str, str]] = None) -> str:
    """Serialize a canonical tree root-first, so the program streams with forward references."""
    counters: Dict[str, int] = {}
    lines: List[str] = []

    def name_for(n: dict, is_root: bool) -> str:
        if is_root:
            return "root"
        p = n.get("props", {})
        key = (names or {}).get(p.get("label") or p.get("title") or p.get("text") or "")
        if key:
            return key
        base = {"Row": "row", "Column": "col", "GeneratedView": "artifact"}.get(n["type"], n["type"].lower())
        counters[base] = counters.get(base, 0) + 1
        return f"{base}{counters[base]}"

    def emit(n: dict, is_root: bool = False) -> str:
        name = name_for(n, is_root)
        slot = len(lines)
        lines.append("")  # reserve: the parent line goes before its children
        kids = [emit(c) for c in n.get("children") or []]
        p = n.get("props") or {}
        t = n["type"]
        if t in ("Row", "Column"):
            gap = {v: k for k, v in GAPS.items()}.get(p.get("gap", "medium"), "m")
            expr = f"Stack([{', '.join(kids)}], {lit('row' if t == 'Row' else 'column')}, {lit(gap)})"
        elif t == "Card":
            args = [lit(p.get("title", "")), f"[{', '.join(kids)}]"] + ([lit(p["subtitle"])] if p.get("subtitle") else [])
            expr = f"Card({', '.join(args)})"
        elif t == "GeneratedView":
            expr = f"HtmlArtifact({lit(p['title'])}, {lit(p['html'])}, {lit(p.get('height', 260))})"
        else:
            params = SIGNATURES[t]
            args = [p.get(k) for k in params]
            while args and args[-1] in (None, {}):
                args.pop()
            expr = f"{t}({', '.join(lit(a) for a in args)})"
        lines[slot] = f"{name} = {expr}"
        return name

    emit(tree, True)
    return "\n".join(lines) + "\n"
