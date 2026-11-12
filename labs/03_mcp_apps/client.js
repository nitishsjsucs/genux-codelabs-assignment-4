// A minimal MCP Apps HOST page: an MCP client (JSON-RPC over HTTP to our
// server), a stand-in for the host's model that picks the tool, and the
// iframe + bridge that runs the server's ui:// resource.

import { shell, mode, autoAction } from "/common/web/shell.js";
import { postJSON } from "/common/web/sse.js";
import { HostBridge, APP_MIME, cspFor, withCsp } from "./bridge.js";

const PROMPT = "How did my solar do this week, and when should I charge the EV?";
const ui = shell({
  lab: "Lab 03 · MCP Apps (io.modelcontextprotocol/ui)",
  title: "MCP Apps: the server ships the UI, the host decides what it may do",
  prompt: PROMPT,
  blurb: {
    static: "The tool show_energy_dashboard points at ui://voltpilot/static-dashboard.html - a view the developer wrote. The tool result carries numbers only; its Schedule button calls an app-only tool through the host.",
    declarative: "The tool render_energy_ui asks the server-side model for a spec, validates it, and returns it in structuredContent. The ui:// view is a generic catalog renderer.",
    open_ended: "The tool generate_energy_view returns model-written HTML. The view mounts it in a NESTED sandbox: host page -> sandboxed view -> sandboxed generated frame.",
    mixed: "A validated spec with catalog components and one GeneratedView. Catalog buttons and the nested frame's button both become tools/call requests that the host allows only for app-visible tools.",
  },
});

let nextId = 1;
async function rpc(method, params = {}) {
  const msg = { jsonrpc: "2.0", id: nextId++, method, params };
  ui.log("out", `host->server ${method}`, params);
  const reply = await postJSON(`/api/03_mcp_apps/${mode}`, msg);
  const summary = method === "resources/read" ? { uri: reply.result?.contents?.[0]?.uri, mimeType: reply.result?.contents?.[0]?.mimeType, bytes: reply.result?.contents?.[0]?.text?.length }
    : method === "tools/list" ? reply.result?.tools?.map((t) => `${t.name} ${JSON.stringify(t._meta?.ui ?? {})}`) : reply.result ?? reply.error;
  ui.log("in", `server->host ${method}`, summary);
  if (reply.error) throw new Error(reply.error.message);
  return reply.result;
}

(async () => {
  await rpc("initialize", { protocolVersion: "2025-06-18", clientInfo: { name: "voltpilot-host", version: "1.0" },
    capabilities: { extensions: { "io.modelcontextprotocol/ui": { mimeTypes: [APP_MIME] } } } });
  const { tools } = await rpc("tools/list");
  // The host's model chooses a tool. Here that choice is scripted: the one tool with a UI the model may call.
  const tool = tools.find((t) => t._meta?.ui?.resourceUri && (t._meta.ui.visibility ?? ["model"]).includes("model"));
  const args = tool.inputSchema?.properties?.question ? { question: PROMPT } : {};
  ui.say("assistant", `(host model) I'll call ${tool.name} - it comes with an interface.`); ui.newBubble();
  const resultPromise = rpc("tools/call", { name: tool.name, arguments: args });

  const content = (await rpc("resources/read", { uri: tool._meta.ui.resourceUri })).contents[0];
  if (content.mimeType !== APP_MIME) throw new Error(`not an MCP App resource: ${content.mimeType}`);
  const iframe = document.createElement("iframe");
  iframe.setAttribute("sandbox", "allow-scripts"); // opaque origin: no cookies, no parent DOM
  iframe.className = "vp-frame";
  iframe.style.height = "420px";
  iframe.title = tool.name;
  iframe.srcdoc = withCsp(content.text, cspFor(content._meta?.ui));
  const card = document.createElement("section");
  card.className = "vp-card";
  card.innerHTML = `<h3>${tool.name}</h3><p class="vp-sub">${content.uri} · ${content.mimeType} · sandbox="allow-scripts" · CSP connect-src 'none'</p>`;
  card.append(iframe);
  ui.surface.replaceChildren(card);

  const bridge = new HostBridge({
    tool, tools,
    callTool: (name, a) => rpc("tools/call", { name, arguments: a }),
    readResource: (uri) => rpc("resources/read", { uri }),
    onMessage: (p) => { ui.say("user", `(from the app) ${p.content?.text ?? ""}`); ui.newBubble(); ui.status("done · app message received", true); },
    onSizeChanged: ({ height }) => { iframe.style.height = `${Math.min(Math.max(height, 160), 1400)}px`; },
    onLog: (dir, m) => ui.log(dir === "view->host" ? "out" : "in", `${dir} ${m.method ?? (m.error ? "error" : "result")}`, m.params ?? m.result ?? m.error ?? {}),
    hostContext: { autoDemo: autoAction },
  }).attach(iframe);
  await bridge.deliver(args, resultPromise);
  ui.status("done · view mounted", true);
})().catch((err) => { ui.say("app", String(err)); ui.status("error", true); });
