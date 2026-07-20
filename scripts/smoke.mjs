// End-to-end smoke test: launches the built MCP server over stdio using the
// official MCP client, then exercises the tools. Proves the full
// host -> TS -> Python worker -> TS -> host path.
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..");

const transport = new StdioClientTransport({
  command: process.execPath, // node
  args: [path.join(ROOT, "dist", "index.js")],
  cwd: ROOT,
  stderr: "inherit",
});

const client = new Client({ name: "smoke", version: "0.0.1" });

function assert(cond, msg) {
  if (!cond) throw new Error("ASSERT FAILED: " + msg);
}

try {
  await client.connect(transport);
  console.log("connected.");

  const tools = await client.listTools();
  const names = tools.tools.map((t) => t.name).sort();
  console.log("tools:", names.join(", "));
  assert(names.includes("ping"), "ping tool registered");
  assert(names.includes("compare_designs"), "compare_designs tool registered");

  const ping = await client.callTool({
    name: "ping",
    arguments: { message: "round-trip" },
  });
  const pingText = ping.content?.[0]?.text ?? "";
  console.log("ping ->", pingText.replace(/\s+/g, " ").slice(0, 200));
  const pingObj = JSON.parse(pingText);
  assert(pingObj.pong === true, "worker replied pong");
  assert(pingObj.echo?.message === "round-trip", "worker echoed our message");

  const cmp = await client.callTool({
    name: "compare_designs",
    arguments: { reference: "a.png", candidate: "b.png", mode: "widget" },
  });
  const cmpObj = JSON.parse(cmp.content[0].text);
  console.log(
    "compare_designs ->",
    JSON.stringify({
      overall: cmpObj.overall,
      subscoreKeys: Object.keys(cmpObj.subscores),
      alignmentMode: cmpObj.alignment?.mode,
      stub: cmpObj.stub,
    }),
  );
  assert(cmpObj.stub === true, "compare_designs returned stub");
  assert(cmpObj.alignment?.mode === "widget", "mode threaded through to worker");
  assert(
    Object.keys(cmpObj.subscores).length === 5,
    "five sub-score dimensions present",
  );

  console.log("\nALL CHECKS PASSED ✅");
  await client.close();
  process.exit(0);
} catch (err) {
  console.error("\nSMOKE TEST FAILED ❌\n", err);
  await client.close().catch(() => {});
  process.exit(1);
}
