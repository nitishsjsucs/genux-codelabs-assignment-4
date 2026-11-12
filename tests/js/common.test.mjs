// node --test: the shared browser modules (no DOM needed for these functions).
import { test } from "node:test";
import assert from "node:assert/strict";
import { applyPatch, applyOp, resolve } from "../../common/web/jsonpatch.js";
import { srcdoc, isActionMessage, CSP } from "../../common/web/sandbox.js";
import { parseFrames } from "../../common/web/sse.js";
import { flatToTree, COMPONENT_NAMES } from "../../common/web/catalog.js";

test("json patch: add/replace/remove/test, escapes and '-'", () => {
  const doc = applyPatch({ a: { b: [1, 2] } }, [
    { op: "add", path: "/a/b/-", value: 3 },
    { op: "add", path: "/a/b/0", value: 0 },
    { op: "replace", path: "/a/b/1", value: 9 },
    { op: "remove", path: "/a/b/2" },
    { op: "add", path: "/x~1y", value: true },
    { op: "test", path: "/x~1y", value: true },
  ]);
  assert.deepEqual(doc, { a: { b: [0, 9, 3] }, "x/y": true });
  assert.throws(() => applyOp({ a: 1 }, { op: "replace", path: "/nope", value: 1 }));
  assert.equal(resolve({ a: [5] }, "/a/0"), 5);
  assert.equal(resolve({}, "/missing", "d"), "d");
});

test("sandbox: CSP is the first thing in the frame", () => {
  const doc = srcdoc("<!doctype html><script>alert(1)</script>");
  assert.ok(doc.indexOf("Content-Security-Policy") < doc.indexOf("alert"));
  assert.match(CSP, /connect-src 'none'/);
  assert.match(srcdoc("<b>x</b>"), /^<!doctype html><meta http-equiv/);
});

test("sandbox: only one message shape, only allow-listed names", () => {
  const allowed = ["schedule_ev_charge"];
  assert.ok(isActionMessage({ type: "voltpilot:action", name: "schedule_ev_charge", params: { window: "x" } }, allowed));
  assert.ok(!isActionMessage({ type: "voltpilot:action", name: "transfer_funds", params: {} }, allowed));
  assert.ok(!isActionMessage({ type: "other", name: "schedule_ev_charge" }, allowed));
  assert.ok(!isActionMessage({ type: "voltpilot:action", name: "schedule_ev_charge", params: [] }, allowed));
  assert.ok(!isActionMessage("schedule_ev_charge", allowed));
});

test("sse: complete frames only, leftover kept", () => {
  const [frames, rest] = parseFrames('data: {"a":1}\n\ndata: {"b":2}\n\ndata: {"c"');
  assert.deepEqual(frames, [{ a: 1 }, { b: 2 }]);
  assert.equal(rest, 'data: {"c"');
});

test("catalog: flat element map to tree, missing children skipped", () => {
  const tree = flatToTree({ root: "r", elements: { r: { type: "Column", children: ["a", "later"] }, a: { type: "Text", props: { text: "hi" } } } });
  assert.equal(tree.children.length, 1);
  assert.equal(tree.children[0].props.text, "hi");
  assert.ok(COMPONENT_NAMES.includes("GeneratedView"));
  assert.throws(() => flatToTree({ root: "r", elements: { r: { type: "Column", children: ["r"] } } }), /cycle/);
});
