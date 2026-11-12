// The harness's WEB surface: the same events the terminal surface prints,
// drawn in a page. Clicks go back into the same harness session.

import { shell, mode, delay, maybeAutoClick, autoAction } from "/common/web/shell.js";
import { postSSE } from "/common/web/sse.js";
import { paint, renderTree } from "/common/web/catalog.js";
import { mountSandbox } from "/common/web/sandbox.js";

const ui = shell({
  lab: "Lab 06 · Harness integration",
  title: "Harness integration: UI tools inside an agent loop",
  prompt: "How did my solar do this week, and when should I charge the EV?",
  blurb: {
    static: "One UI tool, show_component(name, props), over a fixed set of prebuilt components. Each call appends a panel; the same calls print as text in the terminal surface (static.py).",
    declarative: "render_ui(spec) is validated. The first spec has a PieChart and a short table row: the error text goes back to the model as the tool result, and its second attempt renders. Watch the log.",
    open_ended: "render_html(title, html) saves an artifact and emits an html event: sandboxed iframe here, a text fallback in the terminal. The clock's button is injected into the same session.",
    mixed: "render_ui with one GeneratedView. Clicks (catalog or frame) are checked and injected as [ui-action] turns; schedule_ev_charge patches the harness-owned UI state and re-renders.",
  },
});

let session = null;
const panels = [];

function onAction(name, params, origin) { act(name, params, origin); }

async function consume(url, body) {
  for await (const e of postSSE(url, { ...body, delay })) {
    switch (e.kind) {
      case "session": session = e.id; ui.log("in", "session", e.id); break;
      case "text": ui.say("assistant", e.text); ui.newBubble(); ui.log("in", `step ${e.step} · model text`, e.text); break;
      case "tool_call": ui.log("out", `step ${e.step} · tool_call ${e.name}`, e.args); break;
      case "tool_result": ui.log("in", `step ${e.step} · tool_result ${e.ok ? "ok" : "ERROR"}`, e.content); if (!e.ok) { ui.say("app", `tool error returned to the model: ${e.content}`); ui.newBubble(); } break;
      case "render":
        if (e.append) { panels.push(e.tree); paint(ui.surface, { type: "Column", props: { gap: "medium" }, children: panels }, { onAction }); }
        else paint(ui.surface, e.tree, { onAction, allowGenerated: mode === "mixed" });
        ui.log("in", "surface · render", e.component ?? "tree");
        break;
      case "html": {
        const box = renderTree({ type: "Card", props: { title: e.title, subtitle: `${e.bytes} bytes · artifact ${e.artifact} · sandboxed` }, children: [] });
        box.querySelector(".vp-card-body").append(mountSandbox(e.html, { height: 280, title: e.title, onAction }));
        ui.surface.replaceChildren(box);
        ui.log("in", "surface · html", e.artifact);
        break;
      }
      case "notice": ui.surface.prepend(renderTree({ type: "Text", props: { text: e.text, variant: "success" }, children: [] })); break;
      case "action": ui.log("in", "harness · injected action", { name: e.name, params: e.params }); break;
      case "done": ui.log("in", "done", `${e.steps} model calls`); break;
      case "error": ui.log("in", "ERROR", e.message); ui.say("app", e.message); ui.newBubble(); break;
    }
  }
}

async function act(name, params, origin) {
  ui.log("out", `click (${origin}) -> session ${session}`, { name, params });
  ui.status("running");
  await consume(`/api/06_harness/${mode}/action`, { session, action: name, params });
  ui.status("done · action handled", true);
}

(async () => {
  await consume(`/api/06_harness/${mode}`, {});
  ui.status("done", true);
  maybeAutoClick(ui.surface);
  if (mode === "open_ended" && autoAction) setTimeout(() => act("schedule_ev_charge", { window: "10:30-15:00" }, "sandbox (auto)"), 900);
})().catch((err) => { ui.say("app", String(err)); ui.status("error", true); });
