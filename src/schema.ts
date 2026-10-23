import { z } from "zod";
import path from "node:path";

export const ExtractVideoFramesInput = z.object({
  videoPath: z.string().min(1).refine(path.isAbsolute, "videoPath must be an absolute local file path"),
  startMs: z.number().finite().int().min(0).max(Number.MAX_SAFE_INTEGER - 20_000).default(0),
  durationMs: z.number().finite().int().min(1).max(20_000),
  fps: z.number().finite().int().min(1).max(30).default(5),
}).strict().refine(value => Math.ceil(value.durationMs * value.fps / 1000) <= 120, {
  message: "Requested window exceeds 120 samples",
});
export type ExtractVideoFramesInput = z.infer<typeof ExtractVideoFramesInput>;

const VideoSample = z.discriminatedUnion("kind", [
  z.object({ kind: z.literal("selected"), requestedMs: z.number(), frameIndex: z.number().int().nonnegative() }).strict(),
  z.object({ kind: z.literal("shared"), requestedMs: z.number(), frameIndex: z.number().int().nonnegative() }).strict(),
  z.object({ kind: z.literal("unavailable"), requestedMs: z.number() }).strict(),
]);

export const VideoManifest = z.object({
  version: z.literal(1),
  source: z.object({
    path: z.string(), sha256: z.string(), bytes: z.number(), codec: z.string(),
    durationMs: z.number(), width: z.number(), height: z.number(),
    rotationDegrees: z.number(), displayMatrix: z.string().nullable(), displayWidth: z.number(), displayHeight: z.number(),
    timeBase: z.string(), firstPts: z.number(),
  }).strict(),
  versions: z.object({ tool: z.string(), node: z.string(), ffmpeg: z.string(), ffprobe: z.string() }).strict(),
  window: z.object({ startMs: z.number(), durationMs: z.number(), fps: z.number() }).strict(),
  policy: z.literal("first decoded PTS at or after request; half-open window; unique source frames; autorotate; square pixels not rescaled"),
  sampling: z.enum(["complete", "sparse", "incomplete"]),
  frames: z.array(z.object({ path: z.string(), actualMs: z.number(), pts: z.number() }).strict()),
  samples: z.array(VideoSample),
}).strict();
export type VideoManifest = z.infer<typeof VideoManifest>;

export const ExtractVideoFramesResult = z.object({
  dir: z.string(), manifestPath: z.string(), frames: z.array(z.string()), manifest: VideoManifest,
}).strict();
export type ExtractVideoFramesResult = z.infer<typeof ExtractVideoFramesResult>;

/** Comparison rigor. `widget` = tight crop, assume rough alignment, strict.
 *  `screen` = full UI, robust auto-alignment, tolerant + region-based. */
export const CompareMode = z.enum(["widget", "screen"]);
export type CompareMode = z.infer<typeof CompareMode>;

/** Box as [x, y, w, h] in original reference image pixels (before 768 normalization). */
export const Box = z.tuple([z.number(), z.number(), z.number(), z.number()]);

export const ComparisonContext = z.object({
  scopeId: z.string().min(1).max(128).refine(
    value => !/[\uD800-\uDFFF]/u.test(value),
    "scopeId must contain valid Unicode without lone surrogates",
  ),
  protocolKey: z.string().regex(/^[0-9a-f]{64}$/),
}).strict();
export type ComparisonContext = z.infer<typeof ComparisonContext>;

const WEIGHT_KEYS = [
  "layout",
  "color",
  "content",
  "typography",
  "spacing",
] as const;

const WeightsShape = z
  .object({
    layout: z.number().min(0).optional(),
    color: z.number().min(0).optional(),
    content: z.number().min(0).optional(),
    typography: z.number().min(0).optional(),
    spacing: z.number().min(0).optional(),
  })
  .strict()
  .refine(
    (w) => Object.values(w).some((v) => v !== undefined && v > 0),
    { message: "weights must include at least one dimension > 0" },
  );

export const CompareInputShape = {
  reference: z
    .string()
    .describe("Absolute local path to the reference/goal design image (PNG/JPG). Relative paths use the server working directory, not the caller project."),
  candidate: z
    .string()
    .describe(
      "Absolute local path to the candidate image — app screenshot, video frame, or cropped widget. Relative paths use the server working directory.",
    ),
  mode: CompareMode.default("screen").describe(
    "'widget' = tight crop, strict scoring; 'screen' = full UI, tolerant, auto-aligned.",
  ),
  ignoreRegions: Box.array()
    .optional()
    .describe(
      "Regions suppressed by per-image modal-color fill, not true pixel exclusion, as [x,y,w,h] " +
        "in original reference image pixels. The worker scales and clips their union to its " +
        "768px padded canvas; zero/negative-size boxes cover no pixels. Finding boxes are " +
        "always in that canonical 768 canvas space.",
    ),
  comparisonContext: ComparisonContext.optional().describe(
    "Caller-declared scopeId (1-128 UTF-16 code units) and lowercase SHA256 protocolKey for " +
      "an immutable external protocol manifest. Metadata only; does not alter scoring or verify " +
      "capture state, crop origin, or the manifest. When omitted, only supplied pixels/settings are known.",
  ),
  preset: z
    .enum(["default", "dark-ui"])
    .optional()
    .describe(
      "Weighting preset. 'default' = balanced 5-dimension. 'dark-ui' = calibrated for dark, " +
        "single-theme UI ports (layout-dominant, color down-weighted, content/spacing off). " +
        "Explicit `weights` still override individual dimensions.",
    ),
  weights: WeightsShape.optional().describe(
    "Optional per-dimension weight overrides (layout, color, content, typography, spacing) " +
      "for the overall score. Unknown keys are rejected; each value must be >= 0 with at least one > 0.",
  ),
  returnVisuals: z
    .boolean()
    .default(true)
    .describe("Include overlay / side-by-side diagnostic images in the result."),
};

export const CompareInput = z.object(CompareInputShape);
export type CompareInput = z.infer<typeof CompareInput>;

/** A frame sequence: a directory of frames (sorted by name) or explicit paths. */
const FrameSource = z
  .union([z.string(), z.string().array()])
  .describe("Absolute directory of frames (sorted by filename) or an ordered array of absolute frame image paths. Relative paths use the server working directory.");

export const CompareMotionInputShape = {
  reference: FrameSource.describe(
    "Reference frame sequence — a directory of frames or an array of paths (captured over time).",
  ),
  candidate: FrameSource.describe(
    "Candidate frame sequence — a directory of frames or an array of paths.",
  ),
  maxFrames: z
    .number()
    .int()
    .positive()
    .optional()
    .describe("Cap frames loaded per sequence (default 240)."),
  returnVisuals: z
    .boolean()
    .default(true)
    .describe("Include the motion-signature chart (reference vs candidate over time)."),
};

export const CompareMotionInput = z.object(CompareMotionInputShape);
export type CompareMotionInput = z.infer<typeof CompareMotionInput>;

const Point = z.tuple([z.number(), z.number()]);

function isHttpUrl(url: string): boolean {
  try {
    const p = new URL(url);
    return p.protocol === "http:" || p.protocol === "https:";
  } catch {
    return false;
  }
}

export const CaptureFramesInputShape = {
  url: z
    .string()
    .refine(isHttpUrl, {
      message: "url must be http: or https: (file:, data:, and other schemes are rejected)",
    })
    .describe(
      "Page URL to capture (http or https only). Use a local dev server URL for your app " +
        "(e.g. http://localhost:5173/preview). file: and data: URLs are not allowed.",
    ),
  frames: z
    .number()
    .int()
    .min(1)
    .max(120)
    .default(12)
    .describe(
      "Number of frames to capture (1–120). Use frames: 1 for a still screenshot to pass to compare_designs.",
    ),
  intervalMs: z.number().int().min(30).max(2000).default(130).describe("Milliseconds between frames."),
  clip: z
    .object({ x: z.number(), y: z.number(), width: z.number(), height: z.number() })
    .optional()
    .describe("Region to capture (default full viewport). Use to crop to the component preview."),
  viewport: z
    .object({ width: z.number(), height: z.number() })
    .optional()
    .describe("Viewport size in CSS px (default 1440x1600)."),
  waitMs: z
    .number()
    .int()
    .min(0)
    .max(20000)
    .default(1500)
    .describe("Wait after load before capturing, for the page to settle/mount."),
  waitForFlutter: z
    .boolean()
    .default(false)
    .describe(
      "Wait for a Flutter <flutter-view> to mount before capturing (Flutter web apps). " +
        "Timeout is reported in the result (capture still proceeds).",
    ),
  actions: z
    .object({
      click: Point.optional().describe("Click at [x, y] (e.g. navigate an SPA or open a component)."),
      hover: Point.optional().describe("Move the pointer to [x, y] (e.g. reveal a tooltip)."),
      wait: z.number().optional().describe("Wait this many ms after the step."),
    })
    .array()
    .optional()
    .describe("Pre-capture steps run in order to navigate or trigger an interaction before sampling frames."),
  outDir: z
    .string()
    .optional()
    .describe(
      "Directory to write frames to (default: a fresh temp dir). When DESIGN_COMPARE_ALLOWED_ROOTS is set, " +
        "must lie inside one of those roots. Pass its path to compare_motion.",
    ),
};

export const CaptureFramesInput = z.object(CaptureFramesInputShape);
export type CaptureFramesInput = z.infer<typeof CaptureFramesInput>;
