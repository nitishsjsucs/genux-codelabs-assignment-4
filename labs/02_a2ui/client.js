// The A2UI page: read {from, a2ui|error} frames, keep surfaces, draw, relay clicks as A2UI actions.

import { shell, mode, delay, maybeAutoClick, autoAction } from "/common/web/shell.js";
import { postSSE } from "/common/web/sse.js";
import { paint } from "/common/web/catalog.js";
import { SurfaceStore, kindOf, actionMessage, sourceOf } from "./surface.js";

const SID = "voltpilot-week";
const ui = shell({
  lab: "Lab 02 · A2UI v0.9.1 (Agent-to-UI)",
  title: "A2UI: flat components, a separate data model, catalogs the client trusts",
  prompt: "How did my solar do this week, and when should I charge the EV?",
  blurb: {
    static: "The developer's template arrives first (createSurface + updateComponents, from: app). The model may only send updateDataModel - watch each bound value fill in. A model attempt to restructure is refused by the server.",
    declarative: "The model writes the surface: createSurface on the energy catalog, three updateComponents batches (the page draws as each lands), then updateDataModel for the table rows.",
    open_ended: "A2UI has no 'run HTML' component. VoltPilot's own energy-open catalog adds HtmlFrame; the model places one and sends the document via updateDataModel /clock/html. The frame's button returns as an A2UI action.",
    mixed: "Catalog dashboard + HtmlFrame + Buttons. A click becomes an A2UI action message (name, surfaceId, sourceComponentId, context); the model answers with updateDataModel + updateComponents.",
  },
});

const store = new SurfaceStore();
let busy = false;

function draw() {
  if (!store.surfaces.has(SID)) return;
  paint(ui.surface, store.toTree(SID), { onAction: act, allowGenerated: true });
}

async function consume(url, body) {
  for await (const f of postSSE(url, { ...body, delay })) {
    if (f.error) {
      ui.log("in", `${f.from} · REFUSED`, f.error);
      ui.say("app", `refused: ${f.error}`); ui.newBubble();
      continue;
    }
    const kind = kindOf(f.a2ui);
    const detail = kind === "updateComponents" ? f.a2ui[kind].components.map((c) => `${c.id}:${c.component}`).join(", ")
      : kind === "updateDataModel" ? { path: f.a2ui[kind].path, value: f.a2ui[kind].value }
      : f.a2ui[kind];
    ui.log("in", `${f.from} · ${kind}`, detail);
    const problems = store.apply(f.a2ui);
    if (problems.length) ui.log("in", "client refused", problems);
    draw();
  }
}

async function act(name, params, origin) {
  if (busy) return;
  busy = true;
  const source = sourceOf(store, SID, name, origin);
  const msg = actionMessage(name, SID, source, params);
  ui.log("out", "action", msg.action);
  ui.status("running");
  await consume(`/api/02_a2ui/${mode}/action`, msg);
  ui.status("done · action handled", true);
  busy = false;
}

(async () => {
  await consume(`/api/02_a2ui/${mode}`, {});
  ui.status(`done · ${store.surfaces.get(SID)?.components.size ?? 0} components`, true);
  maybeAutoClick(ui.surface); // only once the whole reply (data model included) has arrived
  if (mode === "open_ended" && autoAction) setTimeout(() => act("schedule_ev_charge", { window: "10:30-15:00" }, "sandbox"), 900);
})().catch((err) => { ui.say("app", String(err)); ui.status("error", true); });
