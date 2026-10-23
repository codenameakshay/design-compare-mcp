#!/usr/bin/env node
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { PythonWorker, type WorkerError } from "./worker-client.js";
import { readFileSync } from "node:fs";
import { captureFrames } from "./capture.js";
import { extractVideoFrames } from "./extract-video.js";
import { VideoExtractionError } from "./video-process.js";
import {
  CompareInputShape,
  CompareMotionInputShape,
  CaptureFramesInputShape,
  ExtractVideoFramesInput,
} from "./schema.js";

const worker = new PythonWorker();
const extractionShutdown = new AbortController();
const activeExtractions = new Set<ReturnType<typeof extractVideoFrames>>();

const server = new McpServer({
  name: "design-compare-mcp",
  version: "0.12.0",
});

interface Visual {
  name: string;
  mime_type: string;
  base64: string;
}

type ToolResult = {
  content: Array<
    | { type: "text"; text: string }
    | { type: "image"; data: string; mimeType: string }
  >;
  isError?: boolean;
};

function workerErrorResult(err: unknown): ToolResult | null {
  const werr = (err as { workerError?: WorkerError })?.workerError;
  if (!werr) return null;
  return {
    isError: true,
    content: [
      {
        type: "text",
        text: JSON.stringify({ type: werr.type, message: werr.message }, null, 2),
      },
    ],
  };
}

function resultToContent(result: Record<string, unknown>): ToolResult {
  const visuals = (result.visuals as Visual[] | undefined) ?? [];
  const summary = {
    ...result,
    visuals: visuals.map((v) => ({ name: v.name, mime_type: v.mime_type })),
  };
  const content: ToolResult["content"] = [
    { type: "text", text: JSON.stringify(summary, null, 2) },
  ];
  for (const v of visuals) {
    if (v?.base64) {
      content.push({ type: "image", data: v.base64, mimeType: v.mime_type ?? "image/png" });
    }
  }
  return { content };
}

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
    try {
      const result = await worker.request("ping", { message });
      return {
        content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
      };
    } catch (e) {
      const errResult = workerErrorResult(e);
      if (errResult) return errResult;
      throw e;
    }
  },
);

server.registerTool(
  "compare_designs",
  {
    description:
      "Compare a candidate UI image (app screenshot / video frame / cropped widget) against a " +
      "reference design image. Returns an overall score, five sub-scores (layout, color, content, " +
      "typography, spacing) each with status scored | not_applicable | failed, findings, a canvas " +
      "mapping (reference pixels ↔ 768 normalized space), and diagnostic images. " +
      "Read diagnostics.status and issues before treating scores as product differences. " +
      "Alignment fallback, near-uniform inputs, applied translations and mask fill require review; " +
      "an empty comparison scope is inconclusive even if overall is high. " +
      "provenance.comparison_key identifies reference/settings/runtime; run_key also identifies " +
      "candidate pixels. Re-score baselines when comparison_key changes. Caller-declared " +
      "comparisonContext records external scope/protocol identity without verifying capture. " +
      "ignoreRegions are [x,y,w,h] in original reference image pixels; finding boxes are in the " +
      "canonical 768 canvas. Failed dimensions still contribute a floor to the overall geo-mean. " +
      "Use preset: 'dark-ui' for dark single-theme UI ports. Static comparison cannot judge " +
      "animation — use compare_motion for sampled motion diagnostics, not animation fidelity.",
    inputSchema: CompareInputShape,
  },
  async (args) => {
    try {
      const result = await worker.request<Record<string, unknown>>("compare_designs", args);
      return resultToContent(result);
    } catch (e) {
      const errResult = workerErrorResult(e);
      if (errResult) return errResult;
      throw e;
    }
  },
);

server.registerTool(
  "compare_motion",
  {
    description:
      "Compare the MOTION of a component from two frame sequences (reference vs candidate), each a " +
      "directory of frames or an array of frame paths captured over time. Returns motion energy, " +
      "frame-index profile correlation, motion_status (compared | static | capture_unreliable), " +
      "and motion_energy_score (number or null; motion_score is its compatibility alias). " +
      "Energy similarity does not measure animation fidelity. Read timing_diagnostics separately: " +
      "inputs have no timestamps, so timing is inconclusive and cadence is not verified. " +
      "Unequal-length sequences have no profile correlation; they are never silently truncated. " +
      "Null energy scores mean static or unreliable captures, not a perfect 100. " +
      "Includes a motion-signature chart when returnVisuals is true.",
    inputSchema: CompareMotionInputShape,
  },
  async (args) => {
    try {
      const result = await worker.request<Record<string, unknown>>("compare_motion", args);
      return resultToContent(result);
    } catch (e) {
      const errResult = workerErrorResult(e);
      if (errResult) return errResult;
      throw e;
    }
  },
);

server.registerTool(
  "extract_video_frames",
  {
    description: "Extract PNGs from an absolute local self-contained MP4/MOV path. Samples the half-open window at fps (default 5), at most 20 seconds and 120 requests. Uses actual decoded presentation timestamps, never an fps filter. Returns unique ordered absolute frames and a provenance manifest with selected/shared/unavailable sample mappings. Review sparse/incomplete sampling before comparing motion. No alignment or scoring. Requires ffmpeg and ffprobe on PATH.",
    inputSchema: ExtractVideoFramesInput,
  },
  async (args, { signal }) => {
    const extraction = extractVideoFrames(args, AbortSignal.any([signal, extractionShutdown.signal]));
    activeExtractions.add(extraction);
    try {
      const result = await extraction;
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    } catch (error) {
      return {
        isError: true,
        content: [{ type: "text", text: JSON.stringify({
          type: error instanceof VideoExtractionError ? error.code : "ExtractionError",
          message: error instanceof Error ? error.message : String(error),
        }) }],
      };
    } finally {
      activeExtractions.delete(extraction);
    }
  },
);

server.registerTool(
  "capture_frames",
  {
    description:
      "Capture an ordered frame sequence of a live page over time (headless Chrome), for " +
      "compare_motion or a still (frames: 1) for compare_designs. URL must be http or https. " +
      "Use clip to crop to a preview, actions to navigate/trigger before sampling, and " +
      "waitForFlutter for Flutter web apps — flutter wait outcome is always reported, never swallowed. " +
      "When DESIGN_COMPARE_ALLOWED_ROOTS is set, outDir must lie inside one of those roots " +
      "and should be set explicitly for restricted comparisons. Returns ordered frames, the output directory, blank detection, " +
      "flutterWait when requested, and sample frames. Requires Chrome/Chromium (DESIGN_COMPARE_CHROME).",
    inputSchema: CaptureFramesInputShape,
  },
  async (args) => {
    try {
      const res = await captureFrames(args as Parameters<typeof captureFrames>[0]);
      const summary: Record<string, unknown> = {
        dir: res.dir,
        count: res.count,
        frames: res.frames,
        intervalMs: res.intervalMs,
        url: res.url,
        blank: res.blank,
        note:
          "Pass `dir` to compare_motion as reference or candidate. With frames: 1, pass the frame " +
          "path to compare_designs. Check blank and flutterWait before trusting captures.",
      };
      if (res.flutterWait) summary.flutterWait = res.flutterWait;

      const content: ToolResult["content"] = [
        { type: "text", text: JSON.stringify(summary, null, 2) },
      ];

      const sampleIndices =
        res.count <= 1 ? [0] : [0, res.count - 1];
      for (const idx of sampleIndices) {
        content.push({
          type: "image",
          data: readFileSync(res.frames[idx]).toString("base64"),
          mimeType: "image/png",
        });
      }
      return { content };
    } catch (e) {
      const errResult = workerErrorResult(e);
      if (errResult) return errResult;
      throw e;
    }
  },
);

async function main(): Promise<void> {
  await worker.start();
  const transport = new StdioServerTransport();
  await server.connect(transport);

  process.stdin.on("end", () => shutdown("stdin-eof"));
  process.stdin.on("close", () => shutdown("stdin-close"));

  process.stderr.write("[design-compare-mcp] server ready on stdio\n");
}

let shuttingDown = false;

async function shutdown(reason: string): Promise<void> {
  if (shuttingDown) return;
  shuttingDown = true;
  process.stderr.write(`[design-compare-mcp] shutting down (${reason})\n`);
  extractionShutdown.abort(new Error("Server is shutting down"));
  await Promise.allSettled(activeExtractions);

  const forceExit = setTimeout(() => {
    process.stderr.write("[design-compare-mcp] shutdown timed out; forcing exit\n");
    process.exit(1);
  }, 5000);
  forceExit.unref();

  try {
    await worker.stop();
  } catch {
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
