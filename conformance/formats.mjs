// OpenUI Lang: parse our programs with the official @openuidev/lang-core parser and compare with ours.
// json-render: validate our specs with @json-render/core and resolve their expressions with its resolver.
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { parse } from "@openuidev/lang-core";
import { validateSpec, resolveElementProps } from "@json-render/core";
import { Program, SIGNATURES } from "../labs/05_openui/openui-parse.js";

console.log(execFileSync("python3", ["dump_specs.py"], { encoding: "utf8" }).trim());
let failures = 0;

// ---- OpenUI Lang
const paramMap = new Map(Object.entries(SIGNATURES).map(([name, ps]) => [name, { params: ps.map((p, i) => ({ name: p, required: i === 0 })) }]));
const officialShape = (n) => {
  if (Array.isArray(n)) return n.map(officialShape);
  if (!n || typeof n !== "object") return n;
  if (n.type === "element") {
    const props = {};
    for (const [k, v] of Object.entries(n.props)) if (v !== null && v !== undefined) props[k] = officialShape(v);
    return { component: n.typeName, ...props };
  }
  return Object.fromEntries(Object.entries(n).map(([k, v]) => [k, officialShape(v)]));
};
const ourShape = (v) => {
  if (Array.isArray(v)) return v.map(ourShape);
  if (!v || typeof v !== "object") return v;
  const out = {};
  for (const [k, x] of Object.entries(v)) if (x !== null && x !== undefined) out[k === "__component" ? "component" : k] = ourShape(x);
  return out;
};
const programs = JSON.parse(readFileSync("out/openui_programs.json", "utf8"));
for (const [mode, text] of Object.entries(programs)) {
  const official = parse(text, paramMap, "root");
  const ours = new Program(); ours.feed(text); ours.close();
  const same = JSON.stringify(officialShape(official.root)) === JSON.stringify(ourShape(ours.value(["ref", "root"])));
  const stmts = official.meta.statementCount ?? "?";
  console.log(`  openui ${mode.padEnd(11)} official parse: root=${official.root?.typeName} unresolved=${official.meta.unresolved.length} ` +
    `errors=${(official.meta.errors ?? []).length} statements=${stmts} -> ${same ? "same tree as ours" : "DIFFERENT tree"}`);
  if (!same || !official.root || official.meta.unresolved.length) failures += 1;
}

// ---- json-render
const specs = JSON.parse(readFileSync("out/json_render_specs.json", "utf8"));
for (const [mode, { spec, canonical }] of Object.entries(specs)) {
  const v = validateSpec(spec);
  const errors = v.issues.filter((i) => i.severity === "error");
  // resolve every element's props with the official resolver and compare with ours (Metric/Text values etc.)
  let mismatches = 0;
  const walk = (node) => {
    const el = spec.elements[node.id];
    if (el && !["Button", "CustomHtml"].includes(el.type)) {
      const official = resolveElementProps(el.props ?? {}, { stateModel: spec.state ?? {} });
      for (const [k, val] of Object.entries(official)) if (val !== undefined && JSON.stringify(val) !== JSON.stringify(node.props[k])) mismatches += 1;
    }
    (node.children ?? []).forEach(walk);
  };
  walk(canonical);
  console.log(`  json-render ${mode.padEnd(11)} validateSpec valid=${v.valid} errors=${errors.length} warnings=${v.issues.length - errors.length}; ` +
    `official prop resolution vs ours: ${mismatches} mismatches`);
  if (!v.valid || mismatches) { failures += 1; if (errors.length) console.log("   ", errors.slice(0, 3)); }
}
console.log(failures ? `${failures} check(s) FAILED` : "all format checks passed");
process.exit(failures ? 1 : 0);
