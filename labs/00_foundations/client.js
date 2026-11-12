// Foundations: one POST, one JSON reply, and the app decides how much of it to trust.

import { shell, mode, maybeAutoClick } from "/common/web/shell.js";
import { postJSON } from "/common/web/sse.js";
import { paint, renderTree } from "/common/web/catalog.js";
import { mountSandbox } from "/common/web/sandbox.js";

const ui = shell({
  lab: "Lab 00 · Foundations (no protocol)",
  title: "Four ways to let a model build an interface",
  prompt: "How did my solar do this week, and when should I charge the EV?",
  blurb: {
    static: "The model only names an app component (WeeklySummary) and fills its props. Layout, look and behaviour are the developer's.",
    declarative: "The model composes a tree from the catalog. The app validates every node before drawing; unknown components never render.",
    open_ended: "The model writes HTML+JS. The app cannot validate meaning, so it lints the document and runs it in a sandboxed iframe with no network.",
    mixed: "The recommended default: a catalog tree with one GeneratedView escape hatch, sandboxed. Labs 01-06 deliver exactly these four modes over six technologies.",
  },
});

const onAction = (name, params, origin) => {
  ui.log("out", `action (${origin})`, { name, params });
  ui.surface.prepend(renderTree({ type: "Text", props: { text: `The app received "${name}" ${JSON.stringify(params)} - labs 01-06 send it back to the agent.`, variant: "success" }, children: [] }));
};

(async () => {
  ui.log("out", "POST", `/api/00_foundations/${mode}`);
  const out = await postJSON(`/api/00_foundations/${mode}`, {});
  ui.log("in", `model output · ${out.bytes} bytes`, out.model_output);
  ui.log("in", "app checks", out.errors.length ? out.errors : "passed");
  if (out.tree) paint(ui.surface, out.tree, { onAction, allowGenerated: mode === "mixed" });
  if (out.html) {
    const card = renderTree({ type: "Card", props: { title: "Model-written HTML", subtitle: `${out.bytes} bytes · sandbox="allow-scripts" · CSP connect-src 'none'` }, children: [] });
    card.querySelector(".vp-card-body").append(mountSandbox(out.html, { height: 280, onAction }));
    ui.surface.replaceChildren(card);
  }
  ui.status(`done · ${out.bytes} bytes from the model`, true);
  maybeAutoClick(ui.surface);
})().catch((err) => { ui.say("app", String(err)); ui.status("error", true); });
