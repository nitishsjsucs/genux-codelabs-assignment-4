// RFC 6902 JSON Patch (add, remove, replace, test) - the twin of common/jsonpatch.py.

export function parsePointer(pointer) {
  if (pointer === "") return [];
  if (!pointer.startsWith("/")) throw new Error(`a JSON Pointer starts with '/': ${pointer}`);
  return pointer.slice(1).split("/").map((t) => t.replaceAll("~1", "/").replaceAll("~0", "~"));
}

function index(arr, token, allowEnd) {
  if (token === "-" && allowEnd) return arr.length;
  if (!/^\d+$/.test(token)) throw new Error(`not an array index: ${token}`);
  const i = Number(token);
  if (i > arr.length || (i === arr.length && !allowEnd)) throw new Error(`index ${i} out of range`);
  return i;
}

export function get(doc, pointer) {
  let node = doc;
  for (const t of parsePointer(pointer)) {
    if (Array.isArray(node)) node = node[index(node, t, false)];
    else if (node && typeof node === "object" && t in node) node = node[t];
    else throw new Error(`no value at ${pointer}`);
  }
  return node;
}

export function resolve(doc, pointer, fallback = undefined) {
  try { return get(doc, pointer); } catch { return fallback; }
}

const clone = (v) => (v === undefined ? v : JSON.parse(JSON.stringify(v)));

/** Apply one operation in place; returns the (possibly replaced) document. */
export function applyOp(doc, op) {
  const { op: kind, path } = op;
  if (typeof path !== "string") throw new Error("missing path");
  if ((kind === "add" || kind === "replace") && path === "") return clone(op.value);
  if (kind === "test") {
    if (JSON.stringify(get(doc, path)) !== JSON.stringify(op.value)) throw new Error(`test failed at ${path}`);
    return doc;
  }
  const tokens = parsePointer(path);
  if (!tokens.length) throw new Error("the root cannot be the target");
  let parent = doc;
  for (const t of tokens.slice(0, -1)) {
    if (Array.isArray(parent)) parent = parent[index(parent, t, false)];
    else { if (!(t in parent)) parent[t] = {}; parent = parent[t]; }
  }
  const last = tokens[tokens.length - 1];
  if (kind === "add") {
    if (Array.isArray(parent)) parent.splice(index(parent, last, true), 0, clone(op.value));
    else parent[last] = clone(op.value);
  } else if (kind === "replace") {
    if (Array.isArray(parent)) parent[index(parent, last, false)] = clone(op.value);
    else { if (!(last in parent)) throw new Error(`replace target ${path} does not exist`); parent[last] = clone(op.value); }
  } else if (kind === "remove") {
    if (Array.isArray(parent)) parent.splice(index(parent, last, false), 1);
    else { if (!(last in parent)) throw new Error(`remove target ${path} does not exist`); delete parent[last]; }
  } else throw new Error(`unsupported op ${kind}`);
  return doc;
}

export function applyPatch(doc, ops) {
  for (const op of ops) doc = applyOp(doc, op);
  return doc;
}
