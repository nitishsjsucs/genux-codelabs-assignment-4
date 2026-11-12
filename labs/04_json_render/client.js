// The json-render page: apply each streamed patch, repaint, measure first paint.

import { shell, mode, delay, maybeAutoClick, autoAction } from "/common/web/shell.js";
import { postSSE } from "/common/web/sse.js";
import { paint } from "/common/web/catalog.js";
import { SpecStream, toCanonical } from "./spec-stream.js";

const ui = shell({
  lab: "Lab 04 · json-render (catalog-bound element map + JSON Patch)",
  title: "json-render: the spec streams in, one patch per line",
  prompt: "How did my solar do this week, and when should I charge the EV?",
  blurb: {
    static: "The developer's spec (static_spec.json) arrives whole; every value is a $state/$template expression. The model only streams 'replace /state/...' patches - a write outside /state is refused on the server.",
    declarative: "The model streams the spec: /root, then /elements/<id> parents first, each /state value right after the element that reads it. The page repaints after every line.",
    open_ended: "The open catalog adds CustomHtml. Its html is bound to /state/clock/html; that one patch passes the content policy, then the page mounts it in a sandboxed iframe.",
    mixed: "Catalog + CustomHtml + Buttons with on.press bindings. The same spec also renders in the terminal (run mixed.py). A press posts {action, params} and the model answers with three more patches.",
  },
});

let stream = new SpecStream();
let t0 = performance.now();
let firstPaint = null;
let lines = 0;

function draw() {
  paint(ui.surface, toCanonical(stream.spec), { onAction: act, allowGenerated: mode === "open_ended" || mode === "mixed" });
}

async function consume(url, body) {
  for await (const f of postSSE(url, { ...body, delay })) {
    if (f.spec) { stream = new SpecStream(f.spec); ui.log("in", "app · spec", { elements: Object.keys(f.spec.elements).length }); draw(); continue; }
    if (f.done) { ui.log("in", "app · validated", f.errors.length ? f.errors : "ok"); continue; }
    if (f.error) { ui.log("in", `${f.from} · REFUSED`, f.error); ui.say("app", `refused: ${f.error}`); ui.newBubble(); continue; }
    lines += 1;
    stream.push(f.patch);
    const v = f.patch.value;
    ui.log("in", `${f.patch.op} ${f.patch.path}`, v && typeof v === "object" && v.type ? v.type : v);
    draw();
    if (firstPaint === null && Object.keys(stream.spec.elements).length >= 2) firstPaint = performance.now() - t0;
  }
}

async function act(name, params, origin) {
  ui.log("out", `action (${origin})`, { action: name, params });
  ui.status("running");
  await consume(`/api/04_json_render/${mode}/action`, { action: name, params });
  ui.status("done · action handled", true);
}

(async () => {
  await consume(`/api/04_json_render/${mode}`, {});
  ui.status(`done · ${lines} patch lines · first paint ${firstPaint === null ? "n/a" : `${firstPaint.toFixed(0)} ms`}`, true);
  maybeAutoClick(ui.surface);
  if (mode === "open_ended" && autoAction) setTimeout(() => act("schedule_ev_charge", { window: "10:30-15:00" }, "sandbox (auto)"), 900);
})().catch((err) => { ui.say("app", String(err)); ui.status("error", true); });
