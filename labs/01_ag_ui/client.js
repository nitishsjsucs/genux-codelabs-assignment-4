// A hand-written AG-UI client: POST a RunAgentInput, read SSE events, keep
// messages and state, and draw. One file serves all four modes.
//
//   static       TOOL_CALL_*  -> a prebuilt component per frontend tool
//   declarative  STATE_SNAPSHOT + STATE_DELTA -> state.ui element map -> catalog renderer
//   open_ended   CUSTOM voltpilot.generated_html -> sandboxed iframe
//   mixed        state.ui with a GeneratedView node; buttons start a new run

import { shell, mode, delay, maybeAutoClick } from "/common/web/shell.js";
import { postSSE } from "/common/web/sse.js";
import { applyPatch } from "/common/web/jsonpatch.js";
import { paint, flatToTree, renderTree } from "/common/web/catalog.js";
import { mountSandbox } from "/common/web/sandbox.js";
import { FRONTEND_COMPONENTS } from "./components.js";

const PROMPT = "How did my solar do this week, and when should I charge the EV?";
const ui = shell({
  lab: "Lab 01 · AG-UI (Agent-User Interaction protocol)",
  title: "AG-UI: one event stream between the agent and the page",
  prompt: PROMPT,
  blurb: {
    static: "The page declares frontend tools. The agent calls one; the page draws its own prebuilt component with the arguments as props, then returns a tool result on the next run.",
    declarative: "The UI is shared state. STATE_SNAPSHOT seeds an element map; each add_component call arrives as a STATE_DELTA (JSON Patch) and the page repaints as it grows.",
    open_ended: "The model writes a whole HTML document. AG-UI carries it in a CUSTOM event; the page mounts it in a sandboxed iframe. Its button posts an allow-listed action that starts a new run.",
    mixed: "A catalog tree in state with one GeneratedView node. Catalog buttons and the in-frame button both start a new run; the server patches a confirmation into the tree.",
  },
});

const frontendTools = mode === "static" ? await (await fetch("./frontend_tools.json")).json() : [];
let state = {};
let messages = [{ id: "u1", role: "user", content: PROMPT }];
const panels = []; // static mode: prebuilt components drawn so far

function redraw() {
  const onAction = (name, params, source) => act(name, params, source);
  if (mode === "static") {
    ui.surface.replaceChildren(...panels.map(({ name, tree }) => {
      const wrap = document.createElement("div");
      wrap.className = "prebuilt";
      wrap.innerHTML = `<span class="tag">frontend component · ${name}</span>`;
      wrap.append(renderTree(tree, { onAction }));
      return wrap;
    }));
    return;
  }
  if (mode === "declarative" || mode === "mixed") {
    if (state.ui) paint(ui.surface, flatToTree(state.ui), { onAction, allowGenerated: mode === "mixed" });
  }
}

async function run(forwardedProps = {}) {
  const input = { threadId: "thread-voltpilot", runId: `run-${Math.random().toString(16).slice(2, 10)}`, state, messages, tools: frontendTools, context: [], forwardedProps };
  ui.log("out", "RunAgentInput", { runId: input.runId, messages: messages.length, tools: frontendTools.map((t) => t.name), forwardedProps });
  const byId = new Map();
  const calls = new Map();
  const clientResults = [];
  const assistant = (id) => {
    if (!byId.has(id)) { const m = { id, role: "assistant", content: "" }; byId.set(id, m); messages.push(m); }
    return byId.get(id);
  };
  for await (const ev of postSSE(`/api/01_ag_ui/${mode}`, { ...input, delay })) {
    const brief = { ...ev }; delete brief.type; delete brief.timestamp;
    ui.log("in", ev.type, ev.type === "STATE_SNAPSHOT" ? { keys: Object.keys(ev.snapshot) } : brief);
    switch (ev.type) {
      case "TEXT_MESSAGE_START": ui.newBubble(); assistant(ev.messageId); break;
      case "TEXT_MESSAGE_CONTENT": assistant(ev.messageId).content += ev.delta; ui.say("assistant", ev.delta); break;
      case "TEXT_MESSAGE_END": ui.newBubble(); break;
      case "TOOL_CALL_START": {
        const call = { id: ev.toolCallId, type: "function", function: { name: ev.toolCallName, arguments: "" } };
        (assistant(ev.parentMessageId ?? ev.toolCallId).toolCalls ??= []).push(call);
        calls.set(ev.toolCallId, call);
        break;
      }
      case "TOOL_CALL_ARGS": calls.get(ev.toolCallId).function.arguments += ev.delta; break;
      case "TOOL_CALL_END": {
        const call = calls.get(ev.toolCallId);
        const render = FRONTEND_COMPONENTS[call.function.name];
        if (mode === "static" && render) { // a frontend tool: we execute it by drawing
          panels.push({ name: call.function.name, tree: render(JSON.parse(call.function.arguments)) });
          redraw();
          clientResults.push({ id: `r-${call.id}`, role: "tool", toolCallId: call.id, content: `rendered ${call.function.name}` });
        }
        break;
      }
      case "TOOL_CALL_RESULT": messages.push({ id: ev.messageId, role: "tool", toolCallId: ev.toolCallId, content: ev.content }); break;
      case "STATE_SNAPSHOT": state = ev.snapshot; redraw(); break;
      case "STATE_DELTA": state = applyPatch(state, ev.delta); redraw(); if (state.ev?.status === "scheduled" && mode === "open_ended") note(state.ev.message); break;
      case "CUSTOM":
        if (ev.name === "voltpilot.generated_html") {
          const frame = mountSandbox(ev.value.html, { height: ev.value.height, title: ev.value.title, onAction: (n, p, s) => act(n, p, s) });
          const box = renderTree({ type: "Card", props: { title: ev.value.title, subtitle: `${ev.value.bytes} bytes of model-written HTML · sandbox="allow-scripts" · CSP connect-src 'none'` }, children: [] });
          box.querySelector(".vp-card-body").append(frame);
          ui.surface.replaceChildren(box);
          if (new URLSearchParams(location.search).get("auto") === "1") setTimeout(() => act("schedule_ev_charge", { window: "10:30-15:00" }, "sandbox (auto)"), 900);
        }
        break;
      case "RUN_ERROR": ui.say("app", `run error: ${ev.message}`); ui.newBubble(); break;
    }
  }
  if (clientResults.length) { messages.push(...clientResults); return run(); } // the page answered its tools: next run
  ui.status(`done · ${messages.length} messages in history`, true);
  if (mode === "mixed") maybeAutoClick(ui.surface);
}

function note(text) {
  if (ui.surface.querySelector(".vp-text.success")) return;
  ui.surface.prepend(renderTree({ type: "Text", props: { text, variant: "success" }, children: [] }));
}

async function act(name, params, source) {
  ui.log("out", `action (${source})`, { name, params });
  messages.push({ id: `u-${Date.now()}`, role: "user", content: `[ui-action] ${name} ${JSON.stringify(params, Object.keys(params).sort())}` });
  ui.status("running");
  await run({ action: { name, params } });
}

run().catch((err) => { ui.say("app", String(err)); ui.status("error", true); });
