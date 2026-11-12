# Conformance — our hand-written protocol code vs the official packages

The labs implement every format and transport from scratch so each byte is visible. This folder checks that
those implementations agree with the **official** packages. It is optional: nothing else in the repo needs npm.

```bash
cd conformance && ./check.sh        # npm ci on first run (needs network once), then three checks
```

| Script | Official package (pinned) | What it checks |
|---|---|---|
| [agui.mjs](agui.mjs) + [dump_agui.py](dump_agui.py) | `@ag-ui/core` 0.0.39 | every event our AG-UI server emits in all 4 modes (incl. client-tool follow-up runs and action runs) parses with `EventSchemas`; every `RunAgentInput` with `RunAgentInputSchema` |
| [mcp.mjs](mcp.mjs) | `@modelcontextprotocol/sdk` 1.17.4 | the SDK's `Client` + `StdioClientTransport` launches `labs/03_mcp_apps/mcp_server.py --stdio` for each mode and runs initialize → tools/list → tools/call → resources/read; the resource must be `text/html;profile=mcp-app` |
| [formats.mjs](formats.mjs) + [dump_specs.py](dump_specs.py) | `@openuidev/lang-core` 0.2.18, `@json-render/core` 0.20.0 | the official OpenUI parser parses our four programs with 0 unresolved refs and produces the **same tree** as our parser; `validateSpec()` accepts our four json-render specs and `resolveElementProps()` resolves every element's props to the same values as our resolver |

Recorded run: [docs/outputs/conformance.txt](../docs/outputs/conformance.txt) — 504/504 AG-UI events valid, 4/4 MCP modes OK, 4/4 OpenUI trees identical, 4/4 json-render specs valid with 0 mismatches.

Not covered: A2UI (our messages are checked by our own validator, not the published JSON schemas) and the official React/Lit renderers.
