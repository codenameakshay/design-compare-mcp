#!/usr/bin/env node
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { PythonWorker } from "./worker-client.js";
import { CompareInputShape } from "./schema.js";

const worker = new PythonWorker();

const server = new McpServer({
  name: "design-compare-mcp",
  version: "0.3.0",
});

interface Visual {
  name: string;
  mime_type: string;
  base64: string;
}

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
      "Compare a candidate UI image (app screenshot / video frame / cropped widget) against a " +
      "reference design image. Returns an overall score, per-dimension sub-scores, findings, and " +
      "diagnostic images (overlay, diff heatmap, side-by-side) for assembling a fix punch-list. " +
      "Phase 1 scores structure (SSIM) only; other dimensions are marked pending.",
    inputSchema: CompareInputShape,
  },
  async (args) => {
    const result = await worker.request<Record<string, unknown>>(
      "compare_designs",
      args,
    );

    const visuals = (result.visuals as Visual[] | undefined) ?? [];
    // Keep the text block lean: strip base64 blobs, keep a descriptor. The
    // pixels ride along as image content blocks the host's vision model can see.
    const summary = {
      ...result,
      visuals: visuals.map((v) => ({ name: v.name, mime_type: v.mime_type })),
    };

    const content: Array<
      | { type: "text"; text: string }
      | { type: "image"; data: string; mimeType: string }
    > = [{ type: "text", text: JSON.stringify(summary, null, 2) }];

    for (const v of visuals) {
      if (v?.base64) {
        content.push({
          type: "image",
          data: v.base64,
          mimeType: v.mime_type ?? "image/png",
        });
      }
    }

    return { content };
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
