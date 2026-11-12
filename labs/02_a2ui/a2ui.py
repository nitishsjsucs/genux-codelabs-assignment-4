"""A2UI v0.9.1 with no library: four envelopes, catalogs, a validator and a client-side surface.

A2UI (Agent-to-UI, a2ui.org) separates three things a UI needs:

    createSurface     a surface id + the catalog its components come from
    updateComponents  a FLAT list of components; each has an id and refers to
                      children by id ("child" / "children")
    updateDataModel   values at JSON Pointer paths; components bind to them
                      with {"path": "/report/solar"}
    deleteSurface     remove the surface

Structure and data travel separately, so the agent can change one number with
one small updateDataModel instead of resending the layout.

A2UI deliberately has no "run this HTML" component: an agent may only name
components from a catalog the client trusts. The sanctioned way to add
anything - including a sandboxed HTML frame - is a *custom catalog* with its
own catalogId. That is what the open-ended and mixed modes do.
"""

from __future__ import annotations

import copy
import json
from typing import Dict, Iterator, List, Optional

from common.jsonpatch import PatchError, apply_op, resolve
from common.sse import short

VERSION = "v0.9.1"
BASIC_CATALOG = "https://a2ui.org/specification/v0_9_1/catalogs/basic/catalog.json"
ENERGY_CATALOG = "https://voltpilot.example/a2ui/catalogs/energy/v1/catalog.json"
ENERGY_OPEN_CATALOG = "https://voltpilot.example/a2ui/catalogs/energy-open/v1/catalog.json"

# component -> (required props, optional props). Every component also has "id" and "component".
_BASIC = {
    "Text": ({"text"}, {"variant"}),
    "Row": ({"children"}, {"justify", "align"}),
    "Column": ({"children"}, {"justify", "align"}),
    "Card": ({"child"}, set()),
    "Button": ({"child", "action"}, {"variant"}),
    "Divider": (set(), {"axis"}),
}
_ENERGY = dict(_BASIC, **{
    "Metric": ({"label", "value"}, {"delta", "tone"}),
    "BarChart": ({"title", "labels", "values"}, {"unit"}),
    "Table": ({"columns", "rows"}, set()),
    "Callout": ({"text"}, {"tone"}),
})
_ENERGY_OPEN = dict(_ENERGY, **{"HtmlFrame": ({"title", "html"}, {"height"})})

CATALOGS = {BASIC_CATALOG: _BASIC, ENERGY_CATALOG: _ENERGY, ENERGY_OPEN_CATALOG: _ENERGY_OPEN}
KINDS = ("createSurface", "updateComponents", "updateDataModel", "deleteSurface")


# ------------------------------------------------------------------ builders

def create_surface(surface_id: str, catalog_id: str) -> dict:
    return {"version": VERSION, "createSurface": {"surfaceId": surface_id, "catalogId": catalog_id}}


def update_components(surface_id: str, components: List[dict]) -> dict:
    return {"version": VERSION, "updateComponents": {"surfaceId": surface_id, "components": components}}


def update_data_model(surface_id: str, path: str, value) -> dict:
    return {"version": VERSION, "updateDataModel": {"surfaceId": surface_id, "path": path, "value": value}}


def delete_surface(surface_id: str) -> dict:
    return {"version": VERSION, "deleteSurface": {"surfaceId": surface_id}}


def kind_of(msg: dict) -> Optional[str]:
    found = [k for k in KINDS if k in msg]
    return found[0] if len(found) == 1 else None


# ------------------------------------------------------------------ validation

def validate(msg: dict, catalog_id: Optional[str] = None) -> List[str]:
    """Schema-level problems with one server->client message. `catalog_id` is the surface's catalog."""
    if not isinstance(msg, dict):
        return ["a message must be a JSON object"]
    errors = []
    if msg.get("version") != VERSION:
        errors.append(f"version must be {VERSION!r}")
    kind = kind_of(msg)
    if kind is None:
        return errors + [f"exactly one of {', '.join(KINDS)} is required"]
    body = msg[kind]
    if not isinstance(body, dict) or not isinstance(body.get("surfaceId"), str):
        return errors + [f"{kind}: surfaceId (string) is required"]
    if kind == "createSurface":
        if body.get("catalogId") not in CATALOGS:
            errors.append(f"createSurface: unknown catalogId {body.get('catalogId')!r}")
    elif kind == "updateComponents":
        comps = body.get("components")
        if not isinstance(comps, list) or not comps:
            return errors + ["updateComponents: components must be a non-empty list"]
        catalog = CATALOGS.get(catalog_id or ENERGY_OPEN_CATALOG, {})
        for i, c in enumerate(comps):
            where = f"updateComponents/components/{i}"
            if not isinstance(c, dict) or not isinstance(c.get("id"), str) or not isinstance(c.get("component"), str):
                errors.append(f"{where}: id and component (strings) are required")
                continue
            spec = catalog.get(c["component"])
            if spec is None:
                errors.append(f"{where} ({c['id']}): component {c['component']!r} is not in catalog {catalog_id}")
                continue
            required, optional = spec
            props = set(c) - {"id", "component", "weight"}
            for missing in sorted(required - props):
                errors.append(f"{where} ({c['id']}): missing {missing!r}")
            for extra in sorted(props - required - optional):
                errors.append(f"{where} ({c['id']}): unknown property {extra!r} for {c['component']}")
            if "children" in c and not isinstance(c["children"], list):
                errors.append(f"{where} ({c['id']}): children must be a list of ids")
            if c["component"] == "Button":
                event = (c.get("action") or {}).get("event") if isinstance(c.get("action"), dict) else None
                if not isinstance(event, dict) or not isinstance(event.get("name"), str):
                    errors.append(f"{where} ({c['id']}): action must be {{event: {{name, context}}}}")
    elif kind == "updateDataModel":
        path = body.get("path", "")
        if not isinstance(path, str) or (path and not path.startswith("/")):
            errors.append("updateDataModel: path must be a JSON Pointer")
        if "value" not in body:
            errors.append("updateDataModel: value is required")
    return errors


# ------------------------------------------------------------------ the client's state

class Surface:
    """What a client keeps per surface: a flat component map and a data model."""

    def __init__(self, surface_id: str, catalog_id: str):
        self.id = surface_id
        self.catalog_id = catalog_id
        self.components: Dict[str, dict] = {}
        self.data: dict = {}


class Client:
    """A minimal A2UI client (the Python twin of labs/02_a2ui/surface.js)."""

    def __init__(self):
        self.surfaces: Dict[str, Surface] = {}

    def apply(self, msg: dict) -> List[str]:
        kind = kind_of(msg)
        body = msg.get(kind) if kind else None
        sid = (body or {}).get("surfaceId")
        catalog_id = self.surfaces[sid].catalog_id if sid in self.surfaces else None
        errors = validate(msg, catalog_id)
        if errors:
            return errors
        if kind == "createSurface":
            self.surfaces[sid] = Surface(sid, body["catalogId"])
            return []
        if sid not in self.surfaces:
            return [f"{kind}: no surface {sid!r} - createSurface first"]
        surface = self.surfaces[sid]
        if kind == "updateComponents":
            for c in body["components"]:
                surface.components[c["id"]] = copy.deepcopy(c)  # same id = replace
        elif kind == "updateDataModel":
            path = body.get("path", "")
            try:
                surface.data = apply_op(surface.data, {"op": "add", "path": path, "value": body["value"]}) if path else copy.deepcopy(body["value"])
            except PatchError as error:
                return [f"updateDataModel: {error}"]
        elif kind == "deleteSurface":
            del self.surfaces[sid]
        return []

    def missing_refs(self, sid: str) -> List[str]:
        s = self.surfaces[sid]
        refs = []
        for c in s.components.values():
            refs += c.get("children", []) if isinstance(c.get("children"), list) else []
            refs += [c["child"]] if isinstance(c.get("child"), str) else []
        return sorted(r for r in set(refs) if r not in s.components)

    def to_tree(self, sid: str, root: str = "root") -> dict:
        """The surface as a canonical tree (common/catalog.py), bindings resolved against the data model."""
        s = self.surfaces[sid]
        return to_canonical(s.components, s.data, root)


def bound(value, data):
    """{"path": "/x"} -> the data model value; anything else is a literal."""
    if isinstance(value, dict) and set(value) == {"path"}:
        return resolve(data, value["path"])
    return value


def to_canonical(components: Dict[str, dict], data: dict, root: str = "root") -> dict:
    def text_of(cid: str) -> str:
        c = components.get(cid, {})
        return str(bound(c.get("text", ""), data))

    def build(cid: str) -> dict:
        c = components.get(cid)
        if c is None:
            return {"type": "__pending", "props": {"ref": cid}, "children": []}
        kind = c["component"]
        kids = [build(k) for k in (c.get("children") or [])] if isinstance(c.get("children"), list) else []
        if kind == "Text":
            variant = {"h1": "h1", "h2": "h2", "h3": "h2", "caption": "caption", "success": "success"}.get(c.get("variant"), "body")
            return {"type": "Text", "props": {"text": text_of(cid), "variant": variant}, "children": [], "id": cid}
        if kind in ("Row", "Column"):
            return {"type": kind, "props": {"gap": "medium"}, "children": kids, "id": cid}
        if kind == "Card":
            return {"type": "Card", "props": {}, "children": [build(c["child"])], "id": cid}
        if kind == "Divider":
            return {"type": "Text", "props": {"text": "", "variant": "small"}, "children": [], "id": cid}
        if kind == "Button":
            event = c["action"]["event"]
            params = {k: bound(v, data) for k, v in (event.get("context") or {}).items()}
            return {"type": "Button", "props": {"label": text_of(c["child"]), "action": event["name"], "params": params,
                                                "variant": "secondary" if c.get("variant") == "secondary" else "primary"},
                    "children": [], "id": cid}
        if kind == "Callout":
            return {"type": "Text", "props": {"text": str(bound(c["text"], data)), "variant": "success"}, "children": [], "id": cid}
        if kind == "HtmlFrame":
            return {"type": "GeneratedView", "props": {"title": bound(c["title"], data), "html": bound(c["html"], data) or "",
                                                       "height": c.get("height", 260)}, "children": [], "id": cid}
        props = {k: bound(v, data) for k, v in c.items() if k not in ("id", "component", "child", "children", "weight")}
        return {"type": kind, "props": {k: v for k, v in props.items() if v is not None}, "children": kids, "id": cid}

    return build(root)


def action_message(name: str, surface_id: str, source: str, context: dict, timestamp: str = "2026-11-11T18:00:00Z") -> dict:
    """The client->server message a click produces."""
    return {"version": VERSION, "action": {"name": name, "surfaceId": surface_id, "sourceComponentId": source,
                                           "timestamp": timestamp, "context": context}}


# ------------------------------------------------------------------ the model's text -> messages

def jsonl_messages(pieces: Iterator[tuple]) -> Iterator[dict]:
    """Turn a streamed JSONL reply into messages as soon as each line is complete.

    Lines that are not JSON come back as {"error": ..., "line": ...} so the caller can report them.
    """
    buffer = ""
    for piece in pieces:
        if piece[0] != "text":
            continue
        buffer += piece[1]
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            yield from _parse_line(line)
    yield from _parse_line(buffer)


def _parse_line(line: str) -> Iterator[dict]:
    line = line.strip()
    if not line or line.startswith("```"):
        return
    try:
        yield json.loads(line)
    except json.JSONDecodeError as error:
        yield {"error": f"not JSON: {error}", "line": line[:120]}


def to_jsonl(messages: List[dict]) -> str:
    return "\n".join(json.dumps(m, separators=(",", ":")) for m in messages) + "\n"


def describe(msg: dict) -> str:
    if "error" in msg:
        return f"REJECTED  {msg['error']}"
    kind = kind_of(msg) or "?"
    body = msg.get(kind, {})
    if kind == "createSurface":
        return f"{kind:<17} surface={body['surfaceId']} catalog={body['catalogId'].rsplit('/', 3)[-3]}"
    if kind == "updateComponents":
        names = ", ".join(f"{c['id']}:{c['component']}" for c in body["components"])
        return f"{kind:<17} {len(body['components'])} components  {short(names, 80)}"
    if kind == "updateDataModel":
        return f"{kind:<17} {body.get('path') or '/'} = {short(body.get('value'), 72)}"
    return f"{kind:<17} surface={body.get('surfaceId')}"
