// json-render in the browser: apply streamed patches to a growing spec and
// turn it into a canonical tree. Pure - node --test drives it.

import { applyOp, resolve } from "../../common/web/jsonpatch.js";

/** {"$state": p} -> state value; {"$template": "..${/p}.."} -> string; anything else unchanged (recursively). */
export function resolveValue(v, state) {
  if (v && typeof v === "object" && !Array.isArray(v)) {
    const keys = Object.keys(v);
    if (keys.length === 1 && keys[0] === "$state") return resolve(state, v.$state);
    if (keys.length === 1 && keys[0] === "$template") return v.$template.replace(/\$\{(\/[^}]*)\}/g, (_, p) => String(resolve(state, p, "")));
    return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, resolveValue(x, state)]));
  }
  if (Array.isArray(v)) return v.map((x) => resolveValue(x, state));
  return v;
}

export function toCanonical(spec) {
  const state = spec?.state ?? {};
  const elements = spec?.elements ?? {};
  const build = (id) => {
    const el = elements[id];
    if (!el) return { type: "__pending", props: { ref: id }, children: [] };
    let type = el.type;
    let props = resolveValue(el.props ?? {}, state);
    if (type === "Button") {
      const press = el.on?.press ?? {};
      props = { ...props, action: press.action ?? "", params: resolveValue(press.params ?? {}, state) };
    }
    if (type === "CustomHtml") {
      type = "GeneratedView";
      props = { title: props.title ?? "Custom view", html: props.html ?? "<p>waiting for the document…</p>", height: props.height ?? 260 };
    }
    if (el.visible?.$state && !resolve(state, el.visible.$state)) return { type: "Column", props: {}, children: [] };
    return { type, id, props, children: (el.children ?? []).filter((c) => c in elements).map(build) };
  };
  return spec?.root in elements ? build(spec.root) : { type: "Column", props: {}, children: [] };
}

export class SpecStream {
  constructor(spec = null) { this.spec = spec ? structuredClone(spec) : { root: null, elements: {}, state: {} }; }
  push(op) { this.spec = applyOp(this.spec, op); return this.spec; }
}
