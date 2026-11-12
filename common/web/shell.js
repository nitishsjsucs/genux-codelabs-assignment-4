// The page frame every lab shares: title, mode tabs, the user's prompt,
// a surface where the UI is drawn, and a protocol log of every message.

const MODES = [
  ["static", "1 · Static"],
  ["declarative", "2 · Declarative"],
  ["open_ended", "3 · Open-ended"],
  ["mixed", "4 · Mixed"],
];

export const params = new URLSearchParams(location.search);
export const mode = params.get("mode") ?? "static";
export const delay = Number(params.get("delay") ?? "0.02"); // seconds between streamed chunks
export const autoAction = params.get("auto") === "1";       // click the first action button by itself (screenshots, demos)

export function shell({ lab, title, blurb, prompt }) {
  document.title = `${title} - ${MODES.find(([m]) => m === mode)?.[1] ?? mode}`;
  const tabs = MODES.map(([m, label]) =>
    `<a class="tab ${m === mode ? "on" : ""}" href="?mode=${m}">${label}</a>`).join("");
  document.body.innerHTML = `
    <header class="top">
      <a class="home" href="/">VoltPilot GenUX codelabs</a>
      <div class="lab">${lab}</div>
      <h1>${title}</h1>
      <nav class="tabs">${tabs}</nav>
      <p class="blurb" id="blurb">${blurb?.[mode] ?? ""}</p>
    </header>
    <main class="grid">
      <section class="left">
        <div class="bubble user"><b>You</b> ${prompt}</div>
        <div id="chat"></div>
        <div id="surface" class="surface"><div class="vp-pending">connecting…</div></div>
      </section>
      <aside class="right">
        <div class="loghead"><span>Protocol log</span><span id="status" class="status">running</span></div>
        <ol id="log" class="log"></ol>
      </aside>
    </main>`;
  const logEl = document.getElementById("log");
  const chatEl = document.getElementById("chat");
  let count = 0;
  return {
    surface: document.getElementById("surface"),
    log(direction, label, payload) {
      count += 1;
      const li = document.createElement("li");
      li.className = `dir-${direction}`;
      const text = typeof payload === "string" ? payload : JSON.stringify(payload);
      li.innerHTML = `<span class="arrow">${direction === "in" ? "⬇" : direction === "out" ? "⬆" : "•"}</span><b></b><code></code>`;
      li.querySelector("b").textContent = label;
      li.querySelector("code").textContent = text.length > 220 ? text.slice(0, 217) + "…" : text;
      logEl.append(li);
      logEl.scrollTop = logEl.scrollHeight;
    },
    say(role, text) {
      let last = chatEl.lastElementChild;
      if (!last || last.dataset.role !== role || last.dataset.closed) {
        last = document.createElement("div");
        last.className = `bubble ${role}`;
        last.dataset.role = role;
        last.innerHTML = `<b>${role === "assistant" ? "VoltPilot" : role === "user" ? "You" : "App"}</b> <span></span>`;
        chatEl.append(last);
      }
      last.querySelector("span").textContent += text;
      return { close: () => (last.dataset.closed = "1") };
    },
    newBubble() { const l = chatEl.lastElementChild; if (l) l.dataset.closed = "1"; },
    status(text, done = false) {
      const el = document.getElementById("status");
      el.textContent = text;
      el.classList.toggle("done", done);
      if (done) document.body.dataset.done = "1";
      return count;
    },
  };
}

/** Click the first allow-listed action button once (only with ?auto=1). The button is looked up
 *  at click time, so a repaint in between cannot leave us clicking a stale, detached copy. */
export function maybeAutoClick(root, selector = 'button[data-action="schedule_ev_charge"]', wait = 300) {
  if (!autoAction || root.dataset.autoClicked || !root.querySelector(selector)) return;
  root.dataset.autoClicked = "1";
  setTimeout(() => root.querySelector(selector)?.click(), wait);
}
