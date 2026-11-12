// POST a JSON body and read the reply as Server-Sent Events.
// (EventSource only does GET; agent protocols such as AG-UI POST their input.)

/** Parse SSE text into the JSON payloads of complete frames; returns [payloads, leftover]. Pure. */
export function parseFrames(buffer) {
  const out = [];
  let rest = buffer;
  let cut;
  while ((cut = rest.indexOf("\n\n")) !== -1) {
    const frame = rest.slice(0, cut);
    rest = rest.slice(cut + 2);
    const data = frame.split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trimStart()).join("\n");
    if (data) out.push(JSON.parse(data));
  }
  return [out, rest];
}

export async function* postSSE(url, body) {
  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json", Accept: "text/event-stream" }, body: JSON.stringify(body ?? {}) });
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const [payloads, rest] = parseFrames(buffer);
    buffer = rest;
    for (const p of payloads) yield p;
  }
}

export async function postJSON(url, body) {
  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  return res.json();
}
