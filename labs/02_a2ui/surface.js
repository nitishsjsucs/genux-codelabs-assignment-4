// A2UI v0.9.1 client state with no library - the JS twin of a2ui.py's Client.
// Pure (no DOM), so node --test can drive it.

import { applyOp, resolve } from "../../common/web/jsonpatch.js";

export const VERSION = "v0.9.1";
const BASIC = ["Text", "Row", "Column", "Card", "Button", "Divider"];
const ENERGY = [...BASIC, "Metric", "BarChart", "Table", "Callout"];
export const CATALOGS = {
  "https://a2ui.org/specification/v0_9_1/catalogs/basic/catalog.json": BASIC,
  "https://voltpilot.example/a2ui/catalogs/energy/v1/catalog.json": ENERGY,
  "https://voltpilot.example/a2ui/catalogs/energy-open/v1/catalog.json": [...ENERGY, "HtmlFrame"],
};
const KINDS = ["createSurface", "updateComponents", "updateDataModel", "deleteSurface"];

export const kindOf = (msg) => {
  const found = KINDS.filter((k) => k in (msg ?? {}));
  return found.length === 1 ? found[0] : null;
};

/** {"path": "/x"} -> value in the data model; anything else is a literal. */
export const bound = (v, data) =>
  v && typeof v === "object" && !Array.isArray(v) && Object.keys(v).length === 1 && "path" in v ? resolve(data, v.path) : v;

export class SurfaceStore {
  constructor() { this.surfaces = new Map(); }

  /** Apply one server message; returns a list of problems ([] = applied). */
  apply(msg) {
    if (msg?.version !== VERSION) return [`version must be ${VERSION}`];
    const kind = kindOf(msg);
    if (!kind) return ["exactly one envelope key is required"];
    const body = msg[kind];
    const sid = body?.surfaceId;
    if (kind === "createSurface") {
      if (!(body.catalogId in CATALOGS)) return [`unknown catalog ${body.catalogId}`];
      this.surfaces.set(sid, { id: sid, catalogId: body.catalogId, components: new Map(), data: {} });
      return [];
    }
    const s = this.surfaces.get(sid);
    if (!s) return [`no surface ${sid}`];
    if (kind === "updateComponents") {
      const allowed = CATALOGS[s.catalogId];
      const bad = body.components.filter((c) => !allowed.includes(c.component));
      if (bad.length) return bad.map((c) => `${c.id}: ${c.component} is not in this surface's catalog`);
      for (const c of body.components) s.components.set(c.id, c); // same id replaces
    } else if (kind === "updateDataModel") {
      s.data = body.path ? applyOp(s.data, { op: "add", path: body.path, value: body.value }) : body.value;
    } else if (kind === "deleteSurface") {
      this.surfaces.delete(sid);
    }
    return [];
  }

  /** The surface as a canonical tree for common/web/catalog.js. */
  toTree(sid, root = "root") {
    const s = this.surfaces.get(sid);
    if (!s) return { type: "Column", props: {}, children: [] };
    return toCanonical(s.components, s.data, root);
  }
}

export function toCanonical(components, data, root = "root") {
  const textOf = (id) => String(bound(components.get(id)?.text ?? "", data) ?? "");
  const build = (id) => {
    const c = components.get(id);
    if (!c) return { type: "__pending", props: { ref: id }, children: [] };
    const kids = Array.isArray(c.children) ? c.children.map(build) : [];
    switch (c.component) {
      case "Text": {
        const variant = { h1: "h1", h2: "h2", h3: "h2", caption: "caption" }[c.variant] ?? "body";
        return { type: "Text", id, props: { text: textOf(id), variant }, children: [] };
      }
      case "Row": case "Column": return { type: c.component, id, props: { gap: "medium" }, children: kids };
      case "Card": return { type: "Card", id, props: {}, children: [build(c.child)] };
      case "Divider": return { type: "Text", id, props: { text: "", variant: "small" }, children: [] };
      case "Callout": return { type: "Text", id, props: { text: String(bound(c.text, data) ?? ""), variant: "success" }, children: [] };
      case "Button": {
        const ev = c.action.event;
        const params = Object.fromEntries(Object.entries(ev.context ?? {}).map(([k, v]) => [k, bound(v, data)]));
        return { type: "Button", id, props: { label: textOf(c.child), action: ev.name, params, variant: c.variant === "secondary" ? "secondary" : "primary" }, children: [] };
      }
      case "HtmlFrame":
        return { type: "GeneratedView", id, props: { title: bound(c.title, data), html: bound(c.html, data) ?? "<p>waiting for /clock/html…</p>", height: c.height ?? 260 }, children: [] };
      default: {
        const props = {};
        for (const [k, v] of Object.entries(c)) if (!["id", "component", "child", "children", "weight"].includes(k)) props[k] = bound(v, data);
        return { type: c.component, id, props, children: kids };
      }
    }
  };
  return build(root);
}

/** The client -> server message a click produces. */
export function actionMessage(name, surfaceId, sourceComponentId, context) {
  return { version: VERSION, action: { name, surfaceId, sourceComponentId, timestamp: new Date().toISOString(), context } };
}

/** Which component fired an action: the Button with that event name, else the HtmlFrame. */
export function sourceOf(store, sid, name, origin) {
  const s = store.surfaces.get(sid);
  if (!s) return null;
  for (const c of s.components.values()) {
    if (origin === "sandbox" && c.component === "HtmlFrame") return c.id;
    if (origin !== "sandbox" && c.component === "Button" && c.action?.event?.name === name) return c.id;
  }
  return null;
}
