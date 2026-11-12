"""The server-side half of the open-ended boundary.

Open-ended output (model-written HTML) is never inserted into the app's own
page. It is mounted in an iframe with ``sandbox="allow-scripts"`` (no
``allow-same-origin``: the frame gets an opaque origin, no cookies, no storage,
no access to the parent DOM) and a Content-Security-Policy that forbids every
network request. The browser half is common/web/sandbox.js.

A sandbox *reduces capabilities*; it does not make model output trustworthy.
The frame can still draw a convincing fake login form or a misleading number.
So servers also run ``policy_check()`` - a coarse lint that rejects documents
that try to reach the network or submit forms - and they only act on messages
from the frame that name an allow-listed action.
"""

from __future__ import annotations

import re
from typing import List

CSP = (
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
    "img-src data:; font-src 'none'; connect-src 'none'; frame-src 'none'; "
    "form-action 'none'; base-uri 'none'"
)

# A tiny shim injected into every frame: the only way out is one message shape.
BRIDGE = """<script>
window.voltpilot = {
  action: function (name, params) {
    parent.postMessage({ type: "voltpilot:action", name: String(name), params: params || {} }, "*");
  }
};
</script>"""

_BLOCKLIST = [
    (re.compile(r"""(src|href|action)\s*=\s*["']?\s*(https?:)?//""", re.I), "loads a remote URL"),
    (re.compile(r"\bfetch\s*\(|XMLHttpRequest|WebSocket|EventSource|sendBeacon", re.I), "opens a network connection"),
    (re.compile(r"<\s*form\b", re.I), "contains a form"),
    (re.compile(r"document\.cookie|localStorage|sessionStorage|indexedDB", re.I), "touches browser storage"),
    (re.compile(r"\btop\.location|parent\.location|window\.open\s*\(", re.I), "navigates the parent"),
    (re.compile(r"<\s*(iframe|object|embed)\b", re.I), "nests another frame"),
]

MAX_HTML_BYTES = 60_000


def policy_check(html: str) -> List[str]:
    """Reasons to refuse a generated document ([] = acceptable). Not a security proof."""
    problems = [reason for pattern, reason in _BLOCKLIST if pattern.search(html)]
    if len(html.encode()) > MAX_HTML_BYTES:
        problems.append(f"is larger than {MAX_HTML_BYTES} bytes")
    return problems


def srcdoc(html: str) -> str:
    """The document a sandboxed frame receives: CSP first, then the bridge, then the model's HTML.

    The CSP <meta> goes before anything the model wrote, so no model script runs
    ahead of the policy.
    """
    head = f'<meta http-equiv="Content-Security-Policy" content="{CSP}"><meta charset="utf-8">' + BRIDGE
    doctype = re.match(r"\s*<!doctype[^>]*>", html, re.I)
    if doctype:
        return html[: doctype.end()] + head + html[doctype.end():]
    return "<!doctype html>" + head + html
