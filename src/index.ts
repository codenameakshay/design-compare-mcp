#!/usr/bin/env node
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { PythonWorker } from "./worker-client.js";
import { CompareInputShape } from "./schema.js";

const worker = new PythonWorker();

const server = new McpServer({
  name: "design-compare-mcp",
  version: "0.0.1",
});

// --- ping: smoke-tests the full host -> TS -> Python -> TS -> host round trip.
server.registerTool(
  "ping",
  {
    description:
      "Health check. Round-trips a message through the Python vision worker and returns its reply.",
    inputSchema: {
      message: z
        .string()
        .default("hello")
        .describe("Arbitrary string echoed back by the worker."),
    },
  },
  async ({ message }) => {
    const result = await worker.request("ping", { message });
    return {
      content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
    };
  },
);

// --- compare_designs: Phase 0 returns a stub with the final result shape.
server.registerTool(
  "compare_designs",
  {
    description:
      "Compare a candidate UI image against a reference design image and return sub-scores plus a fix punch-list. " +
      "Phase 0: returns a zeroed stub in the final result shape (no analysis yet).",
    inputSchema: CompareInputShape,
  },
  async (args) => {
    const result = await worker.request("compare_designs", args);
    return {
      content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
    };
  },
);

async function main(): Promise<void> {
  await worker.start();
  const transport = new StdioServerTransport();
  await server.connect(transport);
  // stderr only — stdout is the MCP protocol channel.
  process.stderr.write("[design-compare-mcp] server ready on stdio\n");
}

async function shutdown(): Promise<void> {
  try {
    await worker.stop();
  } finally {
    await server.close().catch(() => {});
    process.exit(0);
  }
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);

main().catch((err) => {
  process.stderr.write(`[design-compare-mcp] fatal: ${String(err?.stack ?? err)}\n`);
  process.exit(1);
});
