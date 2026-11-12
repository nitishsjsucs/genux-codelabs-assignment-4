// Validate our hand-written AG-UI events and RunAgentInputs with the official @ag-ui/core zod schemas.
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { EventSchemas, RunAgentInputSchema } from "@ag-ui/core";

console.log(execFileSync("python3", ["dump_agui.py"], { encoding: "utf8" }).trim());
const runs = JSON.parse(readFileSync("out/agui_events.json", "utf8"));
let ok = 0, bad = 0;
const byType = {};
for (const run of runs) {
  const input = RunAgentInputSchema.safeParse(run.input);
  if (!input.success) { bad += 1; console.log(`  ${run.mode}: RunAgentInput invalid`, input.error.issues[0]); }
  for (const e of run.events) {
    const r = EventSchemas.safeParse(e);
    if (r.success) { ok += 1; byType[e.type] = (byType[e.type] ?? 0) + 1; }
    else { bad += 1; console.log(`  ${run.mode}: ${e.type} invalid`, r.error.issues[0]); }
  }
}
console.log(`@ag-ui/core EventSchemas: ${ok} events valid, ${bad} invalid; RunAgentInputSchema: ${runs.length} inputs checked`);
console.log("  by type:", Object.entries(byType).map(([k, v]) => `${k}=${v}`).join(" "));
process.exit(bad ? 1 : 0);
