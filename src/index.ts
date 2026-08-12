#!/usr/bin/env node
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { PythonWorker } from "./worker-client.js";
import { readFileSync } from "node:fs";
import { captureFrames } from "./capture.js";
import {
  CompareInputShape,
  CompareMotionInputShape,
  CaptureFramesInputShape,
} from "./schema.js";

const worker = new PythonWorker();

const server = new McpServer({
  name: "design-compare-mcp",
  version: "0.10.0",
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

// A worker result carries base64 `visuals`. Keep the text block lean (strip the
// blobs to a descriptor) and attach each image as an MCP image content block the
// host's vision model can actually see.
function resultToContent(result: Record<string, unknown>) {
  const visuals = (result.visuals as Visual[] | undefined) ?? [];
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
      content.push({ type: "image", data: v.base64, mimeType: v.mime_type ?? "image/png" });
    }
  }
  return { content };
}

// --- compare_designs: static image comparison across five dimensions.
server.registerTool(
  "compare_designs",
  {
    description:
      "Compare a candidate UI image (app screenshot / video frame / cropped widget) against a " +
      "reference design image. Returns an overall score, five sub-scores (layout, color, content, " +
      "typography, spacing), findings, and diagnostic images (overlay, diff heatmap, content " +
      "regions, side-by-side) for assembling a fix punch-list. Use `preset: 'dark-ui'` for dark, " +
      "single-theme UI ports. NOTE: static comparison cannot judge animation — for motion " +
      "fidelity use compare_motion.",
    inputSchema: CompareInputShape,
  },
  async (args) => {
    const result = await worker.request<Record<string, unknown>>("compare_designs", args);
    return resultToContent(result);
  },
);

// --- compare_motion: temporal comparison of two frame sequences.
server.registerTool(
  "compare_motion",
  {
    description:
      "Compare the MOTION of a component from two frame sequences (reference vs candidate), each a " +
      "directory of frames or an array of frame paths captured over time. Returns motion energy, " +
      "temporal rhythm (signature correlation), a motion score, and a signature chart. Measures " +
      "animation fidelity — the dimension static image comparison is blind to. Content-agnostic, " +
      "so it works even when the two sources show different example content.",
    inputSchema: CompareMotionInputShape,
  },
  async (args) => {
    const result = await worker.request<Record<string, unknown>>("compare_motion", args);
    return resultToContent(result);
  },
);

// --- capture_frames: browser-driven frame-sequence capture (feeds compare_motion).
server.registerTool(
  "capture_frames",
  {
    description:
      "Capture an ordered frame sequence of a live page over time (headless Chrome), for " +
      "compare_motion. Point it at a component preview URL; use `clip` to crop to the preview, " +
      "`actions` to navigate/trigger (click/hover/wait) before sampling, and `waitForFlutter` for " +
      "Flutter web apps. Returns the output directory (pass it to compare_motion) plus first/last " +
      "sample frames. Typical flow: capture_frames(reference) + capture_frames(candidate) -> " +
      "compare_motion. Requires a local Chrome/Chromium (set DESIGN_COMPARE_CHROME if not found).",
    inputSchema: CaptureFramesInputShape,
  },
  async (args) => {
    const res = await captureFrames(args as Parameters<typeof captureFrames>[0]);
    const summary = {
      dir: res.dir,
      count: res.count,
      intervalMs: res.intervalMs,
      url: res.url,
      note: "Pass `dir` to compare_motion as `reference` or `candidate`. Sample frames (first, last) below — confirm they are not blank and that the last differs from the first (motion present).",
    };
    const content: Array<
      | { type: "text"; text: string }
      | { type: "image"; data: string; mimeType: string }
    > = [{ type: "text", text: JSON.stringify(summary, null, 2) }];
    for (const idx of [0, res.count - 1]) {
      content.push({
        type: "image",
        data: readFileSync(res.frames[idx]).toString("base64"),
        mimeType: "image/png",
      });
    }
    return { content };
  },
);

async function main(): Promise<void> {
  await worker.start();
  const transport = new StdioServerTransport();
  await server.connect(transport);

  // The host owns our lifetime, and it does not always tell us it is leaving:
  // when it quits (or is killed) it simply closes the pipes, and we get
  // reparented to init with no signal. StdioServerTransport only subscribes to
  // stdin 'data'/'error', so nothing else notices that EOF — and the resident
  // Python worker keeps the event loop alive, so we would linger forever.
  // Treating end-of-stdin as "host is gone" is what stops us leaking.
  process.stdin.on("end", () => shutdown("stdin-eof"));
  process.stdin.on("close", () => shutdown("stdin-close"));

  // stderr only — stdout is the MCP protocol channel.
  process.stderr.write("[design-compare-mcp] server ready on stdio\n");
}

let shuttingDown = false;

async function shutdown(reason: string): Promise<void> {
  // EOF and a signal often arrive together; only the first one counts.
  if (shuttingDown) return;
  shuttingDown = true;
  process.stderr.write(`[design-compare-mcp] shutting down (${reason})\n`);

  // Backstop: never let a wedged worker keep this process (and its child)
  // resident. worker.stop() escalates to SIGKILL after 2s, so 5s is slack.
  const forceExit = setTimeout(() => {
    process.stderr.write("[design-compare-mcp] shutdown timed out; forcing exit\n");
    process.exit(1);
  }, 5000);
  forceExit.unref();

  try {
    await worker.stop();
  } catch {
    /* worker already gone */
  } finally {
    await server.close().catch(() => {});
    clearTimeout(forceExit);
    process.exit(0);
  }
}

process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));
process.on("SIGHUP", () => shutdown("SIGHUP"));

main().catch((err) => {
  process.stderr.write(`[design-compare-mcp] fatal: ${String(err?.stack ?? err)}\n`);
  process.exit(1);
});
