"""RFC 6902 JSON Patch (add, remove, replace, test) over RFC 6901 JSON Pointers.

Used by three labs: AG-UI STATE_DELTA, json-render's streamed spec patches, and
the A2UI data model. The JavaScript twin is common/web/jsonpatch.js; the two are
tested against the same cases (tests/test_common.py, common/web/jsonpatch.test.mjs).
"""

from __future__ import annotations

import copy
from typing import Any, List


class PatchError(ValueError):
    pass


def parse_pointer(pointer: str) -> List[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise PatchError(f"a JSON Pointer starts with '/': {pointer!r}")
    return [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")]


def escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _index(container: list, token: str, allow_end: bool) -> int:
    if token == "-" and allow_end:
        return len(container)
    if not token.isdigit():
        raise PatchError(f"not an array index: {token!r}")
    i = int(token)
    if i > len(container) or (i == len(container) and not allow_end):
        raise PatchError(f"index {i} out of range")
    return i


def get(doc: Any, pointer: str) -> Any:
    node = doc
    for token in parse_pointer(pointer):
        if isinstance(node, list):
            node = node[_index(node, token, False)]
        elif isinstance(node, dict):
            if token not in node:
                raise PatchError(f"no member {token!r} at {pointer}")
            node = node[token]
        else:
            raise PatchError(f"cannot descend into a scalar at {pointer}")
    return node


def resolve(doc: Any, pointer: str, default: Any = None) -> Any:
    """get() that returns a default instead of raising - for data bindings."""
    try:
        return get(doc, pointer)
    except (PatchError, IndexError):
        return default


def _parent(doc: Any, pointer: str):
    tokens = parse_pointer(pointer)
    if not tokens:
        raise PatchError("the root cannot be the target of this operation")
    parent = doc
    for token in tokens[:-1]:
        if isinstance(parent, list):
            parent = parent[_index(parent, token, False)]
        elif isinstance(parent, dict):
            parent = parent.setdefault(token, {})  # lenient: streamed specs create containers on the way
        else:
            raise PatchError(f"cannot descend into a scalar at {pointer}")
    return parent, tokens[-1]


def apply_op(doc: Any, op: dict) -> Any:
    """Apply one operation in place and return the (possibly new) document."""
    kind, path = op.get("op"), op.get("path")
    if not isinstance(path, str):
        raise PatchError(f"missing path in {op}")
    if kind in ("add", "replace") and path == "":
        return copy.deepcopy(op["value"])
    if kind == "test":
        if get(doc, path) != op.get("value"):
            raise PatchError(f"test failed at {path}")
        return doc
    parent, token = _parent(doc, path)
    if kind == "add":
        if isinstance(parent, list):
            parent.insert(_index(parent, token, True), copy.deepcopy(op["value"]))
        else:
            parent[token] = copy.deepcopy(op["value"])
    elif kind == "replace":
        if isinstance(parent, list):
            parent[_index(parent, token, False)] = copy.deepcopy(op["value"])
        else:
            if token not in parent:
                raise PatchError(f"replace target {path} does not exist")
            parent[token] = copy.deepcopy(op["value"])
    elif kind == "remove":
        if isinstance(parent, list):
            del parent[_index(parent, token, False)]
        else:
            if token not in parent:
                raise PatchError(f"remove target {path} does not exist")
            del parent[token]
    else:
        raise PatchError(f"unsupported op {kind!r}")
    return doc


def apply_patch(doc: Any, ops: list) -> Any:
    for op in ops:
        doc = apply_op(doc, op)
    return doc
