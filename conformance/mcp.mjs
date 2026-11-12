// Connect the OFFICIAL MCP TypeScript SDK client to our stdlib Python server over stdio,
// for each mode: initialize, tools/list, tools/call, resources/read.
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const ARGS = { static: {}, declarative: { question: "How did my solar do?" }, open_ended: { question: "How did my solar do?" }, mixed: { question: "How did my solar do?" } };
let failures = 0;
for (const mode of Object.keys(ARGS)) {
  const transport = new StdioClientTransport({ command: "python3", args: ["../labs/03_mcp_apps/mcp_server.py", "--stdio", "--mode", mode] });
  const client = new Client({ name: "conformance-check", version: "1.0.0" });
  try {
    await client.connect(transport);
    const { tools } = await client.listTools();
    const uiTool = tools.find((t) => t._meta?.ui?.resourceUri);
    const result = await client.callTool({ name: uiTool.name, arguments: ARGS[mode] });
    const { contents } = await client.readResource({ uri: uiTool._meta.ui.resourceUri });
    const appOnly = tools.filter((t) => (t._meta?.ui?.visibility ?? []).join() === "app").map((t) => t.name);
    console.log(`  ${mode.padEnd(11)} server=${client.getServerVersion()?.name} tools=[${tools.map((t) => t.name)}] ` +
      `call ok=${!result.isError} structured=${Object.keys(result.structuredContent ?? {})} ` +
      `resource=${contents[0].mimeType} ${contents[0].text.length}B app-only=[${appOnly}]`);
    if (result.isError || contents[0].mimeType !== "text/html;profile=mcp-app") failures += 1;
  } catch (error) {
    failures += 1;
    console.log(`  ${mode}: FAILED ${error.message}`);
  } finally {
    await client.close();
  }
}
console.log(`@modelcontextprotocol/sdk client vs our stdio server: ${4 - failures}/4 modes OK`);
process.exit(failures ? 1 : 0);
