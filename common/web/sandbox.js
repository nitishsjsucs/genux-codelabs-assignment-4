// The browser half of the open-ended boundary (the server half is common/sandbox.py).
//
// Model-written HTML is mounted in <iframe sandbox="allow-scripts"> via srcdoc.
// Without allow-same-origin the frame has an opaque origin: it cannot read the
// parent's DOM, cookies or storage. The CSP <meta> forbids every network request.
// The only way out is postMessage, and the parent accepts exactly one shape:
//   { type: "voltpilot:action", name: <allow-listed string>, params: <object> }
// from exactly this frame's window. Everything else is dropped.

export const CSP =
  "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; " +
  "img-src data:; font-src 'none'; connect-src 'none'; frame-src 'none'; " +
  "form-action 'none'; base-uri 'none'";

export const BRIDGE =
  '<script>window.voltpilot={action:function(name,params){parent.postMessage(' +
  '{type:"voltpilot:action",name:String(name),params:params||{}},"*")}};<\/script>'; // <\/ so the file can be inlined in a <script>

/** The frame's document: CSP first (before any model-written byte), then the bridge, then the HTML. */
export function srcdoc(html) {
  const head = `<meta http-equiv="Content-Security-Policy" content="${CSP}"><meta charset="utf-8">${BRIDGE}`;
  const m = /^\s*<!doctype[^>]*>/i.exec(html);
  return m ? html.slice(0, m[0].length) + head + html.slice(m[0].length) : "<!doctype html>" + head + html;
}

/** Is this postMessage payload an action we accept? Pure, so node --test can check it. */
export function isActionMessage(data, allowed) {
  if (!data || typeof data !== "object" || Array.isArray(data)) return false;
  if (data.type !== "voltpilot:action" || typeof data.name !== "string") return false;
  if (data.params !== undefined && (data.params === null || typeof data.params !== "object" || Array.isArray(data.params))) return false;
  return allowed.includes(data.name);
}

export const DEFAULT_ACTIONS = ["schedule_ev_charge", "dismiss"];

/** Mount `html` in a sandboxed frame. Returns the iframe; its listener is removed with `iframe.detach()`. */
export function mountSandbox(html, { height = 260, title = "generated view", onAction, allowed = DEFAULT_ACTIONS } = {}) {
  const iframe = document.createElement("iframe");
  iframe.setAttribute("sandbox", "allow-scripts"); // never allow-same-origin
  iframe.setAttribute("referrerpolicy", "no-referrer");
  iframe.title = title;
  iframe.className = "vp-frame";
  iframe.style.height = `${height}px`;
  iframe.srcdoc = srcdoc(html);
  const listener = (event) => {
    if (event.source !== iframe.contentWindow) return; // only this frame
    if (event.origin !== "null") return;               // a sandboxed srcdoc frame has an opaque origin
    if (!isActionMessage(event.data, allowed)) {
      console.warn("dropped message from sandbox", event.data);
      return;
    }
    onAction?.(event.data.name, event.data.params ?? {}, "sandbox");
  };
  window.addEventListener("message", listener);
  iframe.detach = () => window.removeEventListener("message", listener);
  return iframe;
}
