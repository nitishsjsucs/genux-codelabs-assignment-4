// node --test: the per-lab client modules (A2UI store, json-render stream, OpenUI parser, MCP host bridge).
import { test } from "node:test";
import assert from "node:assert/strict";
import { SurfaceStore, actionMessage, sourceOf } from "../../labs/02_a2ui/surface.js";
import { SpecStream, toCanonical, resolveValue } from "../../labs/04_json_render/spec-stream.js";
import { Program, parseStatement } from "../../labs/05_openui/openui-parse.js";
import { HostBridge, cspFor, withCsp, viewMayCall } from "../../labs/03_mcp_apps/bridge.js";

const V = "v0.9.1";
const ENERGY_OPEN = "https://voltpilot.example/a2ui/catalogs/energy-open/v1/catalog.json";
const BASIC = "https://a2ui.org/specification/v0_9_1/catalogs/basic/catalog.json";

test("a2ui: surface, components, data binding, action", () => {
  const s = new SurfaceStore();
  assert.deepEqual(s.apply({ version: V, createSurface: { surfaceId: "w", catalogId: ENERGY_OPEN } }), []);
  s.apply({ version: V, updateComponents: { surfaceId: "w", components: [
    { id: "root", component: "Column", children: ["m", "b"] },
    { id: "m", component: "Metric", label: "Solar", value: { path: "/s" } },
    { id: "b", component: "Button", child: "bt", action: { event: { name: "schedule_ev_charge", context: { window: { path: "/w" } } } } },
    { id: "bt", component: "Text", text: "Go" },
  ] } });
  s.apply({ version: V, updateDataModel: { surfaceId: "w", path: "/s", value: "133.3 kWh" } });
  s.apply({ version: V, updateDataModel: { surfaceId: "w", path: "/w", value: "10:30-15:00" } });
  const tree = s.toTree("w");
  assert.equal(tree.children[0].props.value, "133.3 kWh");
  assert.deepEqual(tree.children[1].props.params, { window: "10:30-15:00" });
  assert.equal(sourceOf(s, "w", "schedule_ev_charge", "catalog"), "b");
  assert.equal(actionMessage("x", "w", "b", {}).action.surfaceId, "w");
});

test("a2ui: the client also refuses components outside the surface's catalog", () => {
  const s = new SurfaceStore();
  s.apply({ version: V, createSurface: { surfaceId: "b", catalogId: BASIC } });
  const errs = s.apply({ version: V, updateComponents: { surfaceId: "b", components: [{ id: "root", component: "HtmlFrame", title: "x", html: "x" }] } });
  assert.equal(errs.length, 1);
});

test("json-render: patches build a spec that renders half-way", () => {
  const st = new SpecStream();
  st.push({ op: "add", path: "/root", value: "main" });
  st.push({ op: "add", path: "/elements/main", value: { type: "Card", props: { title: { $template: "Hi ${/n}" } }, children: ["x"] } });
  st.push({ op: "add", path: "/state/n", value: "there" });
  const tree = toCanonical(st.spec);
  assert.equal(tree.props.title, "Hi there");
  assert.equal(tree.children.length, 0); // x has not streamed yet
  assert.equal(resolveValue({ $state: "/n" }, st.spec.state), "there");
});

test("openui: forward references, objects, redefinition", () => {
  const p = new Program();
  p.feed('root = Stack([a, b], "row", "s")\n');
  assert.equal(p.tree().children[0].type, "__pending");
  p.feed('a = Button("Go", "schedule_ev_charge", "primary", {window: "10:30-15:00"})\nb = Text("x")\nb = Text("y", "h2")\n');
  const t = p.tree();
  assert.equal(t.type, "Row");
  assert.deepEqual(t.children[0].props.params, { window: "10:30-15:00" });
  assert.equal(t.children[1].props.text, "y");
  assert.throws(() => parseStatement("x = Text(\"a\""), /expected/);
});

test("mcp: CSP builder drops smuggled directives", () => {
  assert.match(cspFor({}), /connect-src 'none'/);
  const csp = cspFor({ csp: { connectDomains: ["https://ok.example", "https://x; script-src *"] } });
  assert.match(csp, /connect-src https:\/\/ok.example/);
  assert.doesNotMatch(csp, /script-src \*/);
  assert.ok(withCsp("<!doctype html><p>x</p>", "default-src 'none'").startsWith("<!doctype html><meta"));
});

test("mcp: host bridge lifecycle and visibility", async () => {
  const sent = [];
  const tools = [{ name: "render", _meta: { ui: { resourceUri: "ui://x" } } }, { name: "book", _meta: { ui: { visibility: ["app"] } } }, { name: "secret", _meta: { ui: { visibility: ["model"] } } }];
  const calls = [];
  const bridge = new HostBridge({ send: (m) => sent.push(m), tool: tools[0], tools, callTool: async (n, a) => { calls.push(n); return { content: [] }; } });
  const init = await bridge.handle({ jsonrpc: "2.0", id: 1, method: "ui/initialize", params: {} });
  assert.equal(init.result.protocolVersion, "2025-06-18");
  await bridge.deliver({ q: 1 }, Promise.resolve({ structuredContent: { ok: true } }));
  assert.equal(sent.length, 0, "notifications wait for ui/notifications/initialized");
  await bridge.handle({ jsonrpc: "2.0", method: "ui/notifications/initialized" });
  assert.deepEqual(sent.map((m) => m.method), ["ui/notifications/tool-input", "ui/notifications/tool-result"]);
  assert.ok((await bridge.handle({ jsonrpc: "2.0", id: 2, method: "tools/call", params: { name: "book" } })).result);
  assert.match((await bridge.handle({ jsonrpc: "2.0", id: 3, method: "tools/call", params: { name: "secret" } })).error.message, /may not call/);
  assert.deepEqual(calls, ["book"]);
  assert.equal(await bridge.handle({ jsonrpc: "1.0", id: 4, method: "ping" }), undefined);
  assert.ok(viewMayCall(tools, "render") && !viewMayCall(tools, "nope"));
});
