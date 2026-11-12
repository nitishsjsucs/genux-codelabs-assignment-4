// OpenUI Lang in the browser - the JS twin of openui.py (tokenizer, parser,
// streaming Program, resolver to the canonical tree). Pure: node --test runs it,
// and tests/test_openui.py checks both parsers give the same tree.

export const SIGNATURES = {
  Stack: ["children", "direction", "gap"],
  Card: ["title", "children", "subtitle"],
  Text: ["text", "variant"],
  Metric: ["label", "value", "delta", "tone"],
  BarChart: ["title", "labels", "values", "unit"],
  Table: ["columns", "rows"],
  Button: ["label", "action", "variant", "params"],
  HtmlArtifact: ["title", "document", "height"],
};
const GAPS = { s: "small", m: "medium", l: "large" };
const TOKEN = /\s+|("(?:[^"\\]|\\.)*")|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|([A-Za-z_][A-Za-z0-9_]*)|([=()[\]{},:])/y;

export function tokenize(line) {
  const out = [];
  TOKEN.lastIndex = 0;
  while (TOKEN.lastIndex < line.length) {
    const at = TOKEN.lastIndex;
    const m = TOKEN.exec(line);
    if (!m) throw new Error(`unexpected character ${JSON.stringify(line[at])} at column ${at + 1}`);
    if (m[1]) out.push(["string", m[1]]);
    else if (m[2]) out.push(["number", m[2]]);
    else if (m[3]) out.push(["name", m[3]]);
    else if (m[4]) out.push(["punct", m[4]]);
  }
  return out;
}

export function parseStatement(line) {
  const t = tokenize(line);
  let i = 0;
  const peek = () => t[i] ?? ["eof", ""];
  const take = (v) => {
    const tok = peek();
    if (v !== undefined && tok[1] !== v) throw new Error(`expected ${v}, found ${tok[1] || "end of line"}`);
    i += 1;
    return tok;
  };
  const items = (close) => {
    const out = [];
    while (peek()[1] !== close) {
      out.push(expr());
      if (peek()[1] === ",") take(",");
      else if (peek()[1] !== close) throw new Error(`expected , or ${close}`);
    }
    take(close);
    return out;
  };
  const expr = () => {
    const [kind, v] = peek();
    if (kind === "string") { take(); return ["lit", JSON.parse(v)]; }
    if (kind === "number") { take(); return ["lit", Number(v)]; }
    if (v === "[") { take("["); return ["arr", items("]")]; }
    if (v === "{") {
      take("{");
      const pairs = [];
      while (peek()[1] !== "}") {
        const [kk, key] = take();
        take(":");
        pairs.push([kk === "string" ? JSON.parse(key) : key, expr()]);
        if (peek()[1] === ",") take(",");
      }
      take("}");
      return ["obj", pairs];
    }
    if (kind === "name") {
      take();
      if (v === "true" || v === "false" || v === "null") return ["lit", { true: true, false: false, null: null }[v]];
      if (peek()[1] === "(") { take("("); return ["call", v, items(")")]; }
      return ["ref", v];
    }
    throw new Error(`unexpected ${v || "end of line"}`);
  };
  const [k, name] = take();
  if (k !== "name") throw new Error(`a statement starts with a name, found ${name}`);
  take("=");
  const value = expr();
  if (peek()[0] !== "eof") throw new Error(`trailing ${peek()[1]}`);
  return [name, value];
}

export class Program {
  constructor() { this.statements = new Map(); this.errors = []; this.buffer = ""; this.lines = 0; }

  /** Add streamed text; returns the names of statements it completed. */
  feed(text) {
    this.buffer += text;
    const done = [];
    let cut;
    while ((cut = this.buffer.indexOf("\n")) !== -1) {
      const name = this.line(this.buffer.slice(0, cut));
      this.buffer = this.buffer.slice(cut + 1);
      if (name) done.push(name);
    }
    return done;
  }

  close() { const n = this.line(this.buffer); this.buffer = ""; return n ? [n] : []; }

  line(raw) {
    const line = raw.trim();
    if (!line || line.startsWith("#") || line.startsWith("//") || line.startsWith("```")) return null;
    this.lines += 1;
    try {
      const [name, value] = parseStatement(line);
      this.statements.set(name, value);
      return name;
    } catch (error) {
      this.errors.push(`line ${this.lines}: ${error.message}`);
      return null;
    }
  }

  value(e, stack = new Set()) {
    switch (e[0]) {
      case "lit": return e[1];
      case "arr": return e[1].map((x) => this.value(x, stack));
      case "obj": return Object.fromEntries(e[1].map(([k, x]) => [k, this.value(x, stack)]));
      case "ref": {
        if (!this.statements.has(e[1])) return { __component: "__pending", ref: e[1] };
        if (stack.has(e[1])) throw new Error(`reference cycle through ${e[1]}`);
        return this.value(this.statements.get(e[1]), new Set(stack).add(e[1]));
      }
      case "call": {
        const params = SIGNATURES[e[1]];
        if (!params) return { __component: "__unknown", name: e[1] };
        const out = { __component: e[1] };
        e[2].forEach((a, i) => { if (i < params.length) out[params[i]] = this.value(a, stack); });
        return out;
      }
    }
    throw new Error("bad expression");
  }

  tree(root = "root") { return toCanonical(this.value(["ref", root])); }
}

export function toCanonical(v) {
  if (!v || typeof v !== "object" || !("__component" in v)) return { type: "Text", props: { text: String(v) }, children: [] };
  const c = v.__component;
  const kids = Array.isArray(v.children) ? v.children.map(toCanonical) : [];
  if (c === "__pending") return { type: "__pending", props: { ref: v.ref }, children: [] };
  if (c === "__unknown") return { type: v.name, props: {}, children: [] };
  if (c === "Stack") return { type: v.direction === "row" ? "Row" : "Column", props: { gap: GAPS[v.gap] ?? "medium" }, children: kids };
  if (c === "HtmlArtifact") return { type: "GeneratedView", props: { title: v.title ?? "", html: v.document ?? "", height: v.height ?? 260 }, children: [] };
  const props = {};
  for (const [k, x] of Object.entries(v)) if (k !== "__component" && k !== "children" && x !== null && x !== undefined) props[k] = x;
  if (c === "Button") props.params ??= {};
  return { type: c, props, children: kids };
}
