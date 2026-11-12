# Video recording script — one video per part

Assignment 4 asks for a YouTube video for each part with a full code walkthrough and the code running. This script
gives each video the same shape (~8–12 minutes): **concept → code → run in the terminal → run in the browser → the
four modes side by side → one failure case → takeaway**. Paste each link into the *Videos* table in the root README.

## Before recording (once)

```bash
python3 run_tests.py                 # show it green at the start of Part 6 (or Part 0)
python3 serve.py                     # leave running in a second terminal: http://127.0.0.1:8765
```
- Browser at 100% zoom, window ≈ 1280×900. Use `&delay=0.05` on a page URL to slow streaming down for the camera.
- Editor with the lab folder open; terminal font large enough to read.
- For each mode, reload the page **without** `&auto=1` and click the button yourself on camera.

---

## Part 0 — Introduction and Lab 00 (Foundations)

1. **Concept (2 min)** — open the root README, section *The two decisions*. Say: "what may the model generate" (static → mixed) is independent of "how does it reach the user" (the six technologies).
2. **Code (3 min)** — `labs/00_foundations/foundations.py`: `APP_COMPONENTS`, then `handle()` line by line — the trust decision per mode. Show `common/catalog.py validate_tree()` and `common/sandbox.py policy_check()`/`srcdoc()`.
3. **Run** — `python3 labs/00_foundations/mixed.py`; point at the byte table (166 → 5,531).
4. **Browser** — the four tabs at `/labs/00_foundations/`. In open-ended, point at the dashed sandbox border.
5. **Takeaway** — mixed is the default: catalog where possible, one sandboxed region where not.

## Part 1 — AG-UI (Lab 01)

1. **Concept** — AG-UI is a transport: RunAgentInput in, typed events out over SSE. Show the event table in `labs/01_ag_ui/README.md`.
2. **Code** — `agui.py run_agent()` (the loop), `execute()` (failures become results), `check_sequence()`; then `client.js` `switch (ev.type)`.
3. **Static** — `python3 labs/01_ag_ui/static.py`; point at RUN 1 ending without `TOOL_CALL_RESULT`, RUN 2 after the page's results. Browser: the "frontend component" tags.
4. **Declarative** — show `add_component()` returning two JSON Patch ops; in the browser watch the log fill with `STATE_DELTA` while the dashboard grows.
5. **Open-ended** — `render_html()` → `CUSTOM`; click the clock's button; show the new `RunAgentInput` with `forwardedProps.action`.
6. **Mixed** — click *Schedule*; show the three patch ops and the green confirmation.
7. **Failure case** — the terminal output's forged `delete_account` → `RUN_ERROR`.
8. **Proof** — `node conformance/agui.mjs` (504 events valid with the official `@ag-ui/core`).

## Part 2 — A2UI (Lab 02)

1. **Concept** — four envelopes; flat components; data model with `{"path": ...}`; catalogs the client trusts. Why A2UI has no HTML component.
2. **Code** — `a2ui.py validate()`, `Client.apply()`, `to_canonical()`; `a2ui_surfaces.py relay()` (mode policy).
3. **Static** — `[app]` messages then `[model] updateDataModel` only; the refused `updateComponents` at the end of the transcript.
4. **Declarative** — three `updateComponents` batches; watch placeholders become components in the browser.
5. **Open-ended** — the energy-open catalog's `HtmlFrame`; the transcript line showing HtmlFrame refused on the basic catalog.
6. **Mixed** — click *Schedule*; show the A2UI `action` message in the log and the `Callout` inserted by `updateComponents`.

## Part 3 — MCP Apps (Lab 03)

1. **Concept** — host / server / view; `_meta.ui.resourceUri`; `text/html;profile=mcp-app`; the postMessage JSON-RPC lifecycle (draw it from the README diagram).
2. **Code** — `mcp_server.py MCPServer.dispatch()`, `ui_tool()`, `bundle()` (why scripts are inlined); `bridge.js HostBridge` and `viewMayCall()`; `views/app_bridge.js`.
3. **Static** — `python3 labs/03_mcp_apps/static.py`: `content` vs `structuredContent`; view may call `schedule_ev_charge`, model may not.
4. **Declarative / open-ended / mixed** — in the browser log follow: initialize → tools/list → tools/call → resources/read → ui/initialize → initialized → tool-input → tool-result → (click) tools/call → ui/message. Point out the **nested** sandbox in open-ended and mixed.
5. **Proof** — `python3 labs/03_mcp_apps/mcp_server.py --stdio --mode mixed` exists for desktop hosts; run `node conformance/mcp.mjs` (official SDK client, 4/4 modes).

## Part 4 — json-render (Lab 04)

1. **Concept** — flat element map + state; why patches stream and nested JSON does not.
2. **Code** — `jsonrender.py resolve_value()`, `to_canonical()`, `SpecStream.push()` (write gate), `spec_to_patches()` ordering.
3. **Static** — the developer's `static_spec.json`; model writes `/state` only; the refused `/elements/ad`.
4. **Declarative** — slow the page down (`&delay=0.08`) and watch each patch line render; the status bar's first-paint time.
5. **Open-ended** — `CustomHtml` bound to `/state/clock/html`; the refused remote-image document in the transcript.
6. **Mixed** — run `mixed.py` and show the **terminal renderer** next to the browser: one spec, two renderers. Click *Schedule*: three patches.

## Part 5 — OpenUI Lang (Lab 05)

1. **Concept** — one statement per line, positional args, forward references, redefinition as edit.
2. **Code** — `openui.py` tokenizer → `_Parser` → `Program.feed()/pending()/tree()`; the JS twin; the parity test.
3. **Static** — `use_template` + `fill()`; the injection attempt that stays a string.
4. **Declarative** — the *pending refs* column rising and falling; the 45% character saving (and why that is not a latency claim).
5. **Open-ended** — `HtmlArtifact`; the dropped remote-script artifact.
6. **Mixed** — click *Schedule*: the reply is two statements; `root` re-declared.
7. **Proof** — `node conformance/formats.mjs` (official parser, same trees).

## Part 6 — Harness integration (Lab 06), tests and wrap-up

1. **Concept** — the loop the other labs plug into; UI tools; surfaces.
2. **Code** — `harness.py Harness.run()` (bounded loop), `execute()`, `ui()`, `inject_action()`; `hx_tools.py` tools.
3. **Static** — three `show_component` calls rendered in the terminal surface.
4. **Declarative** — the self-correction loop: error result with both problems, corrected spec, render. Then the browser page showing the same story.
5. **Open-ended** — artifact saved under `labs/06_harness/out/artifacts/`; terminal fallback vs sandboxed web surface.
6. **Mixed** — click on the web surface; show the injected `[ui-action]` turn and the re-render.
7. **Wrap-up** — `python3 run_tests.py`, `python3 run_all.py`, `cd conformance && ./check.sh`; the comparison table; limitations.
