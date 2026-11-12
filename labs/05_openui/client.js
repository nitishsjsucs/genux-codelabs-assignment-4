// The OpenUI Lang page: parse the program as it streams, draw placeholders for
// forward references, replace them as their statements arrive.

import { shell, mode, delay, maybeAutoClick, autoAction } from "/common/web/shell.js";
import { postSSE } from "/common/web/sse.js";
import { paint } from "/common/web/catalog.js";
import { Program } from "./openui-parse.js";

const ui = shell({
  lab: "Lab 05 · OpenUI Lang",
  title: "OpenUI Lang: a compact program, parsed while it streams",
  prompt: "How did my solar do this week, and when should I charge the EV?",
  blurb: {
    static: "The developer wrote templates/*.oui with {{slots}}. The model only calls use_template(name, values); the app json-encodes each value into a literal, so data can never become structure.",
    declarative: "The model writes the program. Line 1 is root = Stack([...]) - four references to names not defined yet. The parser draws placeholders and fills each as its line arrives.",
    open_ended: "HtmlArtifact(title, document, height) carries a whole HTML document as one string. The server checks it when the statement completes; the page runs it in a sandboxed iframe.",
    mixed: "Catalog statements, one HtmlArtifact, and Buttons with params objects. After a press the model replies with two statements - a new Text and a re-declared root - and the page re-resolves.",
  },
});

const program = new Program();
const refused = new Set();

function draw() {
  paint(ui.surface, program.tree(), { onAction: act, allowGenerated: mode === "open_ended" || mode === "mixed" });
}

async function consume(url, body) {
  for await (const f of postSSE(url, { ...body, delay })) {
    if (f.template) { ui.log("in", "app · template", { name: f.template, slots: f.slots }); continue; }
    if (f.done) { ui.log("in", "app · checked", f.errors.length ? f.errors : `ok · ${f.statements} statements`); continue; }
    if (f.error) {
      ui.log("in", `${f.from} · REFUSED`, f.error); ui.say("app", `refused: ${f.error}`); ui.newBubble();
      if (f.drop) refused.add(f.drop);
      continue;
    }
    for (const name of program.feed(f.chunk)) {
      if (refused.has(name)) { program.statements.delete(name); continue; }
      const e = program.statements.get(name);
      ui.log("in", `${name} =`, e[0] === "call" ? `${e[1]}(…)` : e[0]);
      draw();
    }
  }
  for (const name of program.close()) ui.log("in", `${name} =`, "(last line)");
  draw();
}

async function act(name, params, origin) {
  ui.log("out", `action (${origin})`, { action: name, params });
  ui.status("running");
  await consume(`/api/05_openui/${mode}/action`, { action: name, params });
  ui.status("done · action handled", true);
}

(async () => {
  await consume(`/api/05_openui/${mode}`, {});
  ui.status(`done · ${program.statements.size} statements${program.errors.length ? ` · ${program.errors.length} parse errors` : ""}`, true);
  maybeAutoClick(ui.surface);
  if (mode === "open_ended" && autoAction) setTimeout(() => act("schedule_ev_charge", { window: "10:30-15:00" }, "sandbox (auto)"), 900);
})().catch((err) => { ui.say("app", String(err)); ui.status("error", true); });
