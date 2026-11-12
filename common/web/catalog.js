// The shared DOM renderer: canonical tree -> elements.
//
// Every lab converts its own wire format (AG-UI state, A2UI components,
// json-render elements, an OpenUI program, a harness spec) into the same
// canonical node {type, props, children} and hands it here. The registry below
// IS the client-side half of the catalog: a type that is not in it is drawn as
// a visible error, never guessed at.

import { mountSandbox, DEFAULT_ACTIONS } from "./sandbox.js";

const h = (tag, attrs = {}, ...kids) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v);
  }
  for (const kid of kids.flat()) if (kid) el.append(kid);
  return el;
};

const SVG = "http://www.w3.org/2000/svg";
const s = (tag, attrs = {}) => {
  const el = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  return el;
};

function barChart(p) {
  const labels = p.labels ?? [], values = p.values ?? [];
  const W = 520, H = 190, pad = 26, top = Math.max(...values, 1);
  const bw = (W - pad * 2) / Math.max(values.length, 1);
  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, class: "vp-chart", role: "img", "aria-label": p.title ?? "chart" });
  values.forEach((v, i) => {
    const bh = ((H - 50) * v) / top, x = pad + i * bw + bw * 0.18, y = H - 24 - bh;
    svg.append(s("rect", { x, y, width: bw * 0.64, height: bh, rx: 4, class: "vp-bar" }));
    const val = s("text", { x: x + bw * 0.32, y: y - 5, "text-anchor": "middle", class: "vp-bar-val" });
    val.textContent = String(v);
    const lab = s("text", { x: x + bw * 0.32, y: H - 8, "text-anchor": "middle", class: "vp-bar-lab" });
    lab.textContent = labels[i] ?? "";
    svg.append(val, lab);
  });
  return h("figure", { class: "vp-figure" }, h("figcaption", { text: `${p.title ?? ""}${p.unit ? ` (${p.unit})` : ""}` }), svg);
}

export const RENDERERS = {
  Column: (p, kids) => h("div", { class: `vp-col gap-${p.gap ?? "medium"}` }, kids),
  Row: (p, kids) => h("div", { class: `vp-row gap-${p.gap ?? "medium"}` }, kids),
  Card: (p, kids) =>
    h("section", { class: "vp-card" },
      p.title ? h("h3", { text: p.title }) : null,
      p.subtitle ? h("p", { class: "vp-sub", text: p.subtitle }) : null,
      h("div", { class: "vp-card-body" }, kids)),
  Text: (p) => {
    const tag = p.variant === "h1" ? "h1" : p.variant === "h2" ? "h2" : "p";
    return h(tag, { class: `vp-text ${p.variant ?? "body"}`, text: String(p.text ?? "") });
  },
  Metric: (p) =>
    h("div", { class: `vp-metric ${p.tone ?? ""}` },
      h("div", { class: "vp-metric-label", text: p.label ?? "" }),
      h("div", { class: "vp-metric-value", text: String(p.value ?? "") }),
      p.delta ? h("div", { class: "vp-metric-delta", text: p.delta }) : null),
  BarChart: (p) => barChart(p),
  Table: (p) =>
    h("table", { class: "vp-table" },
      h("thead", {}, h("tr", {}, (p.columns ?? []).map((c) => h("th", { text: String(c) })))),
      h("tbody", {}, (p.rows ?? []).map((r) => h("tr", {}, r.map((c) => h("td", { text: String(c) })))))),
  Button: (p, _kids, ctx) =>
    h("button", {
      class: `vp-btn ${p.variant ?? "primary"}`, text: p.label ?? "",
      "data-action": p.action ?? "",
      onclick: () => ctx.onAction?.(p.action, p.params ?? {}, "catalog"),
    }),
  GeneratedView: (p, _kids, ctx) => {
    if (ctx.allowGenerated === false) return h("div", { class: "vp-error", text: "GeneratedView is not allowed in this mode" });
    const frame = mountSandbox(String(p.html ?? ""), { height: p.height ?? 260, title: p.title, onAction: ctx.onAction, allowed: ctx.allowedActions ?? DEFAULT_ACTIONS });
    return h("div", { class: "vp-generated" },
      h("div", { class: "vp-generated-head" }, h("span", { text: p.title ?? "Generated view" }), h("span", { class: "vp-badge", text: "sandboxed · generated" })),
      frame);
  },
  // A reference the stream has not defined yet (OpenUI forward references, json-render children).
  __pending: (p) => h("div", { class: "vp-pending", text: `waiting for ${p.ref ?? "…"}` }),
};

export const COMPONENT_NAMES = Object.keys(RENDERERS).filter((k) => !k.startsWith("__"));

/** Draw a canonical node. Unknown types become a visible error box. */
export function renderTree(node, ctx = {}) {
  if (!node || typeof node !== "object") return h("div", { class: "vp-error", text: "not a component" });
  const render = RENDERERS[node.type];
  if (!render) return h("div", { class: "vp-error", text: `Unknown component "${node.type}" - not in the catalog` });
  const kids = (node.children ?? []).map((c) => renderTree(c, ctx));
  return render(node.props ?? {}, kids, ctx);
}

/** {root, elements:{id:{type,props,children:[ids]}}} -> canonical tree. Missing children are skipped (still streaming). */
export function flatToTree(spec, resolveProps = (p) => p) {
  const elements = spec?.elements ?? {};
  const build = (id, seen) => {
    if (seen.has(id)) throw new Error(`cycle at ${id}`);
    const el = elements[id];
    const next = new Set(seen).add(id);
    return {
      type: el.type, id,
      props: resolveProps(el.props ?? {}, el),
      children: (el.children ?? []).filter((c) => c in elements).map((c) => build(c, next)),
    };
  };
  if (!spec || !(spec.root in elements)) return { type: "Column", props: {}, children: [] };
  return build(spec.root, new Set());
}

/** Replace a container's content with a freshly rendered tree. */
export function paint(container, tree, ctx) {
  container.querySelectorAll("iframe").forEach((f) => f.detach?.());
  container.replaceChildren(renderTree(tree, ctx));
}
