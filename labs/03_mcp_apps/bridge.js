// The HOST side of the MCP Apps bridge. DOM-free (send/receive are injected),
// so node --test drives it with plain objects; attach() wires it to an iframe.
//
// Lifecycle:  view -> ui/initialize            host answers with hostContext + capabilities
//             view -> ui/notifications/initialized
//             host -> ui/notifications/tool-input   (held until initialized)
//             host -> ui/notifications/tool-result
//             view -> tools/call | resources/read | ui/message | ui/notifications/size-changed

export const APP_MIME = "text/html;profile=mcp-app";
export const PROTOCOL_VERSION = "2025-06-18";

export const RESTRICTIVE_CSP = {
  "default-src": ["'none'"], "script-src": ["'self'", "'unsafe-inline'"], "style-src": ["'self'", "'unsafe-inline'"],
  "img-src": ["'self'", "data:"], "font-src": ["'self'"], "connect-src": ["'none'"], "frame-src": ["'none'"],
  "object-src": ["'none'"], "base-uri": ["'self'"],
};

/** A declared domain may not smuggle a directive in (no ; space or quotes). */
export const isDomain = (v) => typeof v === "string" && v.length > 0 && !/[;\s'"]/.test(v);

/** The restrictive default plus whatever the resource's _meta.ui.csp declares. */
export function cspFor(uiMeta = {}) {
  const d = Object.fromEntries(Object.entries(RESTRICTIVE_CSP).map(([k, v]) => [k, [...v]]));
  const allow = (name, list) => {
    const clean = (Array.isArray(list) ? list : []).filter(isDomain);
    if (clean.length) d[name] = d[name].filter((x) => x !== "'none'").concat(clean);
  };
  allow("connect-src", uiMeta?.csp?.connectDomains);
  allow("frame-src", uiMeta?.csp?.frameDomains);
  return Object.entries(d).map(([k, v]) => `${k} ${v.join(" ")}`).join("; ");
}

/** Put the CSP <meta> first - before any byte of the view runs. */
export function withCsp(html, csp) {
  const meta = `<meta http-equiv="Content-Security-Policy" content="${csp.replaceAll('"', "&quot;")}">`;
  const m = /^\s*<!doctype[^>]*>/i.exec(html);
  return m ? html.slice(0, m[0].length) + meta + html.slice(m[0].length) : meta + html;
}

/** May the VIEW call this tool? Only tools the server listed whose visibility includes "app". */
export function viewMayCall(tools, name) {
  const t = tools.find((x) => x.name === name);
  return Boolean(t) && (t._meta?.ui?.visibility ?? ["model", "app"]).includes("app");
}

export class HostBridge {
  constructor({ send, tool, tools, callTool, readResource, onMessage, onSizeChanged, onLog, hostContext = {} }) {
    Object.assign(this, { send, tool, tools: tools ?? [tool], callTool, readResource, onMessage, onSizeChanged, onLog, hostContext });
    this.initialized = false;
    this.queue = [];
  }

  /** One message from the view -> the reply to post back (or undefined for notifications / junk). */
  async handle(msg) {
    if (!msg || typeof msg !== "object" || msg.jsonrpc !== "2.0") return undefined;
    if (msg.id !== undefined && typeof msg.id !== "string" && typeof msg.id !== "number") return undefined;
    if (typeof msg.method !== "string") return undefined;
    this.onLog?.("view->host", msg);
    const params = msg.params && typeof msg.params === "object" ? msg.params : {};
    if (msg.id === undefined) { this.notification(msg.method, params); return undefined; }
    try {
      return { jsonrpc: "2.0", id: msg.id, result: await this.dispatch(msg.method, params) };
    } catch (error) {
      return { jsonrpc: "2.0", id: msg.id, error: { code: -32000, message: error.message } };
    }
  }

  notification(method, params) {
    if (method === "ui/notifications/initialized") {
      this.initialized = true;
      for (const m of this.queue.splice(0)) this.post(m);
    } else if (method === "ui/notifications/size-changed") {
      this.onSizeChanged?.(params);
    }
  }

  async dispatch(method, params) {
    switch (method) {
      case "ui/initialize":
        return {
          protocolVersion: PROTOCOL_VERSION,
          hostInfo: { name: "voltpilot-host", version: "1.0.0" },
          hostCapabilities: { serverTools: {}, serverResources: {}, message: { text: {} } },
          hostContext: { theme: "light", displayMode: "inline", platform: "web", locale: "en-US", toolInfo: { tool: this.tool }, ...this.hostContext },
        };
      case "tools/call":
        if (!viewMayCall(this.tools, params.name)) throw new Error(`the view may not call ${params.name}`);
        return this.callTool(params.name, params.arguments ?? {});
      case "resources/read":
        if (typeof params.uri !== "string" || !params.uri.startsWith("ui://")) throw new Error("the view may read ui:// resources only");
        return this.readResource(params.uri);
      case "ui/message":
        await this.onMessage?.(params);
        return {};
      case "ping":
        return {};
      default:
        throw new Error(`unsupported method ${method}`);
    }
  }

  post(msg) { this.onLog?.("host->view", msg); this.send(msg); }

  notify(method, params) {
    const msg = { jsonrpc: "2.0", method, params };
    if (this.initialized) this.post(msg); else this.queue.push(msg);
  }

  /** Deliver the call's input now and its result when it settles. */
  async deliver(args, resultPromise) {
    this.notify("ui/notifications/tool-input", { arguments: args });
    try { this.notify("ui/notifications/tool-result", await resultPromise); }
    catch (error) { this.notify("ui/notifications/tool-cancelled", { reason: error.message }); }
  }

  /** Wire to a real iframe: read only messages whose source is that frame. */
  attach(iframe) {
    this.send = (m) => iframe.contentWindow?.postMessage(m, "*");
    const listener = (event) => {
      if (event.source !== iframe.contentWindow) return;
      this.handle(event.data).then((reply) => reply && this.post(reply));
    };
    window.addEventListener("message", listener);
    this.detach = () => window.removeEventListener("message", listener);
    return this;
  }
}
