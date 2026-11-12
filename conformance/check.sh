#!/bin/sh
# Optional conformance run: our hand-written protocol code vs the official SDKs (needs npm + network once).
set -e
cd "$(dirname "$0")"
[ -d node_modules ] || npm ci --no-audit --no-fund
node agui.mjs
node mcp.mjs
node formats.mjs
