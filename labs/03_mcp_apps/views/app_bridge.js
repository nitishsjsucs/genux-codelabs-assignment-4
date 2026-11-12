// The VIEW side of the MCP Apps bridge (inlined into every ui:// resource).
// The view lives in a sandboxed iframe inside the host. It speaks JSON-RPC 2.0
// over postMessage to window.parent - and only reads messages whose source is
// window.parent, so a nested generated frame cannot impersonate the host.

const appBridge = (() => {
  let nextId = 1;
  const pending = new Map();
  const handlers = {};
  window.addEventListener("message", (event) => {
    if (event.source !== window.parent) return; // the host only
    const msg = event.data;
    if (!msg || msg.jsonrpc !== "2.0") return;
    if (msg.method === undefined && msg.id !== undefined) { // a response to one of our requests
      pending.get(msg.id)?.(msg);
      pending.delete(msg.id);
      return;
    }
    if (msg.method === "ui/resource-teardown" && msg.id !== undefined) {
      window.parent.postMessage({ jsonrpc: "2.0", id: msg.id, result: {} }, "*");
      return;
    }
    handlers[msg.method]?.(msg.params ?? {});
  });
  const request = (method, params) => {
    const id = nextId++;
    window.parent.postMessage({ jsonrpc: "2.0", id, method, params }, "*");
    return new Promise((resolve, reject) =>
      pending.set(id, (m) => (m.error ? reject(new Error(m.error.message)) : resolve(m.result))));
  };
  const notify = (method, params) => window.parent.postMessage({ jsonrpc: "2.0", method, params }, "*");
  const on = (method, fn) => { handlers[method] = fn; };
  async function start(appInfo) {
    const init = await request("ui/initialize", {
      appInfo, appCapabilities: { availableDisplayModes: ["inline"] }, protocolVersion: "2025-06-18",
    });
    notify("ui/notifications/initialized", {});
    const report = () => notify("ui/notifications/size-changed", { width: document.body.scrollWidth, height: document.documentElement.scrollHeight + 8 });
    new ResizeObserver(report).observe(document.body);
    report();
    return init;
  }
  return { request, notify, on, start };
})();

/** Call an app-visible server tool through the host; show its text in `statusEl`. */
async function callTool(name, args, statusEl) {
  try {
    const result = await appBridge.request("tools/call", { name, arguments: args });
    const text = result.content?.map((c) => c.text).join(" ") ?? "";
    if (statusEl) { statusEl.textContent = text; statusEl.className = result.isError ? "vp-error" : "vp-text success"; }
    return result;
  } catch (error) {
    if (statusEl) { statusEl.textContent = `refused by host: ${error.message}`; statusEl.className = "vp-error"; }
    return null;
  }
}
