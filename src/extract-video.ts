import { constants } from "node:fs";
import { chmod, mkdtemp, open, readFile, realpath, rm, unlink, writeFile } from "node:fs/promises";
import path from "node:path";
import os from "node:os";
import { createHash } from "node:crypto";
import { z } from "zod";
import { allowedRoots, assertReadableFile, registerServerTempDir } from "./path-and-url-guard.js";
import { ExtractVideoFramesInput, ExtractVideoFramesResult, VideoManifest } from "./schema.js";
import { runVideoProcess, VideoExtractionError } from "./video-process.js";

export const VIDEO_LIMITS = Object.freeze({
  inputBytes: 512 * 1024 * 1024,
  outputBytes: 256 * 1024 * 1024,
  framePixels: 16_000_000,
  dimension: 12_000,
  decodedFrames: 12_000,
  decodedPixels: 12_000_000_000,
  outputPixels: 480_000_000,
  timeoutMs: 60_000,
  concurrentCalls: 2,
});

const NumericText = z.string().transform(Number).pipe(z.number().finite());
const Probe = z.object({
  format: z.object({ start_time: NumericText }),
  frames: z.array(z.object({ pts: z.number().int().safe(), width: z.number().int(), height: z.number().int() })).min(1),
  streams: z.array(z.object({
    codec_name: z.string(), width: z.number().int().positive(), height: z.number().int().positive(),
    time_base: z.string().regex(/^\d+\/\d+$/), start_pts: z.number().int().safe(), duration: NumericText,
    sample_aspect_ratio: z.string().optional(),
    side_data_list: z.array(z.object({ rotation: z.number().optional(), displaymatrix: z.string().optional() })).default([]),
    tags: z.object({ rotate: NumericText.optional() }).optional(),
  })).length(1),
});

let activeCalls = 0;

async function freshDirectory(): Promise<string> {
  const roots = allowedRoots();
  for (const root of roots.length ? roots : [os.tmpdir()]) {
    try {
      const dir = await mkdtemp(path.join(await realpath(root), "dcm-video-"));
      await chmod(dir, 0o700);
      return dir;
    } catch { }
  }
  throw new VideoExtractionError("DisallowedPath", "No permitted writable output root. Make a DESIGN_COMPARE_ALLOWED_ROOTS directory writable; output cannot fall back outside the allowlist.");
}

async function snapshotSource(source: string, destination: string, deadline: number, signal?: AbortSignal) {
  signal?.throwIfAborted();
  const input = await open(source, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const stat = await input.stat();
    if (!stat.isFile()) throw new VideoExtractionError("InvalidVideo", "videoPath must be a regular file");
    if (stat.size > VIDEO_LIMITS.inputBytes) throw new VideoExtractionError("ResourceLimit", "Source exceeds 512 MiB");
    const output = await open(destination, "wx", 0o600);
    try {
      const hash = createHash("sha256");
      const buffer = Buffer.alloc(1024 * 1024);
      let bytes = 0;
      for (;;) {
        signal?.throwIfAborted();
        if (Date.now() >= deadline) throw new VideoExtractionError("ResourceLimit", "Source copy exceeded deadline");
        const read = await input.read(buffer);
        if (read.bytesRead === 0) break;
        bytes += read.bytesRead;
        if (bytes > VIDEO_LIMITS.inputBytes) throw new VideoExtractionError("ResourceLimit", "Source exceeds 512 MiB");
        const chunk = buffer.subarray(0, read.bytesRead);
        hash.update(chunk);
        let written = 0;
        while (written < chunk.length) {
          signal?.throwIfAborted();
          written += (await output.write(chunk.subarray(written))).bytesWritten;
        }
      }
      signal?.throwIfAborted();
      if (bytes !== stat.size || (await input.stat()).mtimeMs !== stat.mtimeMs) throw new VideoExtractionError("InvalidVideo", "Source changed during extraction; retry with an unchanged file");
      return { bytes, sha256: hash.digest("hex") };
    } finally { await output.close(); }
  } finally { await input.close(); }
}

function splitPngs(data: Buffer, width: number, height: number): Buffer[] {
  const images: Buffer[] = [];
  let offset = 0;
  while (offset < data.length) {
    const begin = offset;
    if (!data.subarray(offset, offset + 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))) throw new VideoExtractionError("DecodeFailure", "Decoder did not return a PNG sequence");
    offset += 8;
    let ended = false;
    while (offset + 12 <= data.length) {
      const size = data.readUInt32BE(offset);
      const type = data.toString("ascii", offset + 4, offset + 8);
      if (offset + size + 12 > data.length) break;
      if (type === "IHDR" && (size !== 13 || data.readUInt32BE(offset + 8) !== width || data.readUInt32BE(offset + 12) !== height)) throw new VideoExtractionError("DecodeFailure", "Decoded dimensions changed or orientation was not applied as expected");
      offset += size + 12;
      if (type === "IEND") { ended = true; break; }
    }
    if (!ended) throw new VideoExtractionError("DecodeFailure", "Incomplete PNG output");
    images.push(data.subarray(begin, offset));
    if (images.length > 120 || images.length * width * height > VIDEO_LIMITS.outputPixels) throw new VideoExtractionError("ResourceLimit", "Extracted frames exceed output pixel/sample limits");
  }
  return images;
}

export async function extractVideoFrames(value: unknown, signal?: AbortSignal): Promise<ExtractVideoFramesResult> {
  signal?.throwIfAborted();
  const input = ExtractVideoFramesInput.parse(value);
  if (activeCalls >= VIDEO_LIMITS.concurrentCalls) throw new VideoExtractionError("ResourceLimit", "At most two video extractions can run concurrently; retry after one finishes");
  activeCalls++;
  let dir: string | undefined;
  const deadline = Date.now() + VIDEO_LIMITS.timeoutMs;
  try {
    let source: string;
    try { source = assertReadableFile(input.videoPath); }
    catch (error) { throw new VideoExtractionError("DisallowedPath", String(error)); }
    if (![".mp4", ".mov"].includes(path.extname(source).toLowerCase())) throw new VideoExtractionError("InvalidVideo", "v1 supports only self-contained local .mp4 or .mov recordings");
    dir = await freshDirectory();
    const snapshot = path.join(dir, "source.snapshot");
    const identity = await snapshotSource(source, snapshot, deadline, signal);
    const ffmpeg = process.env.DESIGN_COMPARE_FFMPEG || "ffmpeg";
    const ffprobe = process.env.DESIGN_COMPARE_FFPROBE || "ffprobe";
    const processVideo = (binary: string, args: string[], maxOutputBytes = 1024 * 1024) => runVideoProcess({ binary, args, deadline, maxOutputBytes, signal });
    const ffmpegVersion = (await processVideo(ffmpeg, ["-version"])).stdout.toString("utf8").split("\n")[0];
    const ffprobeVersion = (await processVideo(ffprobe, ["-version"])).stdout.toString("utf8").split("\n")[0];
    const sourceOptions = ["-protocol_whitelist", "file", "-format_whitelist", "mov", "-f", "mov", "-enable_drefs", "0", "-use_absolute_path", "0"];
    const probed = await processVideo(ffprobe, ["-v", "error", "-max_alloc", "67108864", "-threads", "1", "-max_pixels", String(VIDEO_LIMITS.framePixels), ...sourceOptions,
      "-select_streams", "v:0", "-read_intervals", "%+#32", "-show_frames", "-show_streams", "-show_entries",
      "frame=pts,width,height:stream=codec_name,width,height,time_base,start_pts,duration,sample_aspect_ratio:stream_side_data=rotation,displaymatrix:stream_tags=rotate:format=start_time", "-of", "json", snapshot]);
    const parsed = Probe.safeParse(JSON.parse(probed.stdout.toString("utf8")));
    if (!parsed.success) throw new VideoExtractionError("InvalidVideo", "No supported video stream with finite duration and presentation timestamps");
    const stream = parsed.data.streams[0];
    const first = parsed.data.frames[0];
    const [num, den] = stream.time_base.split("/").map(Number);
    if (!Number.isSafeInteger(num) || !Number.isSafeInteger(den) || num <= 0 || den <= 0) throw new VideoExtractionError("InvalidVideo", "Invalid source time base");
    const secondsPerTick = num / den;
    const origin = first.pts * secondsPerTick;
    const durationMs = stream.duration * 1000 + (stream.start_pts - first.pts) * secondsPerTick * 1000;
    const { width, height } = stream;
    if (width * height > VIDEO_LIMITS.framePixels || Math.max(width, height) > VIDEO_LIMITS.dimension) throw new VideoExtractionError("ResourceLimit", "Source exceeds 16 megapixels or 12000 pixels per side");
    if (parsed.data.frames.some(frame => frame.width !== width || frame.height !== height)) throw new VideoExtractionError("InvalidVideo", "Variable source dimensions are unsupported");
    if (stream.sample_aspect_ratio && !["1:1", "0:1"].includes(stream.sample_aspect_ratio)) throw new VideoExtractionError("InvalidVideo", "Non-square pixel recordings are unsupported; export square pixels first");
    const endMs = input.startMs + input.durationMs;
    if (durationMs <= 0 || endMs > durationMs + 0.000001) throw new VideoExtractionError("UnavailableWindow", `Requested half-open window [${input.startMs}, ${endMs}) ms is outside source duration ${durationMs} ms`);
    const rotationDegrees = stream.side_data_list.find(item => item.rotation !== undefined)?.rotation ?? stream.tags?.rotate ?? 0;
    if (!Number.isFinite(rotationDegrees) || Math.abs(rotationDegrees % 90) > 0.000001) throw new VideoExtractionError("InvalidVideo", "Only orthogonal recording rotation is supported");
    const swapped = Math.abs(rotationDegrees % 180) === 90;
    const displayWidth = swapped ? height : width;
    const displayHeight = swapped ? width : height;
    const minimumPts = (millisecondsTimesFps: bigint) => {
      const numerator = millisecondsTimesFps * BigInt(den);
      const denominator = BigInt(input.fps) * 1000n * BigInt(num);
      const pts = first.pts + Number((numerator + denominator - 1n) / denominator);
      if (!Number.isSafeInteger(pts)) throw new VideoExtractionError("InvalidVideo", "Source timing exceeds safe integer PTS range");
      return pts;
    };
    const requested = Array.from({ length: Math.ceil(input.durationMs * input.fps / 1000) }, (_, index) => ({
      requestedMs: input.startMs + index * 1000 / input.fps,
      minimumPts: minimumPts(BigInt(input.startMs) * BigInt(input.fps) + BigInt(index) * 1000n),
    }));
    const startPts = minimumPts(BigInt(input.startMs) * BigInt(input.fps));
    const endPts = minimumPts(BigInt(endMs) * BigInt(input.fps));
    const startSeconds = origin + input.startMs / 1000;
    const relativeStart = startSeconds - parsed.data.format.start_time;
    const seekSeconds = Math.max(0, Math.floor(relativeStart * 1000) / 1000 - 0.001);
    const selection = requested.map(request => `(gte(pts,${request.minimumPts})*if(isnan(prev_pts),1,lt(prev_pts,${request.minimumPts})))`).join("+");
    const filter = `showinfo@decoded,trim=start_pts=${startPts}:end_pts=${endPts},select='${selection}',showinfo@selected`;
    const timestamps: number[] = [];
    let decodedFrames = 0;
    let decodedPixels = 0;
    let previousPts: number | undefined;
    let pendingLine = "";
    const decoded = await runVideoProcess({ binary: ffmpeg, deadline, maxOutputBytes: VIDEO_LIMITS.outputBytes, signal,
      args: ["-hide_banner", "-nostdin", "-nostats", "-loglevel", "info", "-xerror", "-max_alloc", "67108864", "-filter_threads", "1", "-copyts",
        "-threads", "1", "-max_pixels", String(VIDEO_LIMITS.framePixels), ...sourceOptions,
        "-ss", String(seekSeconds), "-t", String(input.durationMs / 1000 + relativeStart - seekSeconds + 0.001), "-i", snapshot,
        "-map", "0:v:0", "-an", "-sn", "-dn", "-vf", filter, "-fps_mode", "passthrough", "-c:v", "png", "-threads:v", "1", "-map_metadata", "-1", "-f", "image2pipe", "pipe:1"],
      onStderr: text => {
        pendingLine += text;
        const lines = pendingLine.split("\n");
        pendingLine = lines.pop() ?? "";
        for (const line of lines) {
          if (line.includes("showinfo@decoded") && /\bn:\s*\d+/.test(line)) {
            decodedFrames++;
            const ptsMatch = /\bpts:\s*(-?\d+)/.exec(line);
            const pts = ptsMatch ? Number(ptsMatch[1]) : NaN;
            if (!Number.isSafeInteger(pts) || (previousPts !== undefined && pts <= previousPts)) throw new VideoExtractionError("InvalidVideo", "Missing, duplicate, or non-monotonic decoded source timestamps");
            previousPts = pts;
            const dimensions = /\bs:(\d+)x(\d+)/.exec(line);
            if (!dimensions) throw new VideoExtractionError("DecodeFailure", "Missing decoded dimensions");
            const w = Number(dimensions[1]), h = Number(dimensions[2]);
            decodedPixels += w * h;
            if (w !== displayWidth || h !== displayHeight) throw new VideoExtractionError("InvalidVideo", "Variable decoded dimensions are unsupported");
            if (decodedFrames > VIDEO_LIMITS.decodedFrames || decodedPixels > VIDEO_LIMITS.decodedPixels) throw new VideoExtractionError("ResourceLimit", "Decoded work exceeds frame/pixel budget");
          }
          if (line.includes("showinfo@selected") && /\bn:\s*\d+/.test(line)) {
            const match = /\bpts:\s*(-?\d+)/.exec(line);
            if (!match || !Number.isSafeInteger(Number(match[1]))) throw new VideoExtractionError("InvalidVideo", "Missing or unsafe source PTS");
            timestamps.push(Number(match[1]));
            if (timestamps.length > 120 || timestamps.length * displayWidth * displayHeight > VIDEO_LIMITS.outputPixels) throw new VideoExtractionError("ResourceLimit", "Selected frames exceed output pixel/sample limits");
          }
          if (line.includes("config in time_base:") && !line.includes(`time_base: ${stream.time_base},`)) throw new VideoExtractionError("InvalidVideo", "Decoder changed presentation time base");
        }
      },
    });
    const pngs = splitPngs(decoded.stdout, displayWidth, displayHeight);
    if (!pngs.length || pngs.length !== timestamps.length) throw new VideoExtractionError("UnavailableWindow", "Window has no decodable selected frames or has incomplete decoder output");
    const frames: VideoManifest["frames"] = [];
    for (const [index, png] of pngs.entries()) {
      signal?.throwIfAborted();
      if (Date.now() >= deadline) throw new VideoExtractionError("ResourceLimit", "Frame export exceeded deadline");
      const pts = timestamps[index];
      const actualMs = (pts - first.pts) * num * 1000 / den;
      if (pts < startPts || pts >= endPts || (index > 0 && pts <= timestamps[index - 1])) throw new VideoExtractionError("InvalidVideo", "Non-monotonic or out-of-window source timestamps");
      const framePath = path.join(dir, `frame_${String(index).padStart(3, "0")}.png`);
      await writeFile(framePath, png, { flag: "wx", mode: 0o444, signal });
      frames.push({ path: framePath, actualMs, pts });
    }
    const used = new Set<number>();
    const samples: VideoManifest["samples"] = requested.map(({ requestedMs, minimumPts }) => {
      const frameIndex = frames.findIndex(frame => frame.pts >= minimumPts);
      if (frameIndex < 0) return { kind: "unavailable", requestedMs };
      const kind = used.has(frameIndex) ? "shared" : "selected";
      used.add(frameIndex);
      return { kind, requestedMs, frameIndex };
    });
    const packageInfo = z.object({ version: z.string() }).parse(JSON.parse(await readFile(new URL("../package.json", import.meta.url), "utf8")));
    const manifest = VideoManifest.parse({
      version: 1,
      source: { path: source, ...identity, codec: stream.codec_name, durationMs, width, height, rotationDegrees,
        displayMatrix: stream.side_data_list.find(item => item.displaymatrix)?.displaymatrix ?? null,
        displayWidth, displayHeight, timeBase: stream.time_base, firstPts: first.pts },
      versions: { tool: `design-compare-mcp/${packageInfo.version}`, node: process.version, ffmpeg: ffmpegVersion, ffprobe: ffprobeVersion },
      window: { startMs: input.startMs, durationMs: input.durationMs, fps: input.fps },
      policy: "first decoded PTS at or after request; half-open window; unique source frames; autorotate; square pixels not rescaled",
      sampling: samples.some(sample => sample.kind === "unavailable") ? "incomplete" : samples.some(sample => sample.kind === "shared") ? "sparse" : "complete",
      frames, samples,
    });
    const manifestPath = path.join(dir, "manifest.json");
    await writeFile(manifestPath, JSON.stringify(manifest, null, 2) + "\n", { flag: "wx", mode: 0o444, signal });
    await unlink(snapshot);
    if (Date.now() >= deadline) throw new VideoExtractionError("ResourceLimit", "Video extraction exceeded deadline");
    await chmod(dir, 0o555);
    signal?.throwIfAborted();
    registerServerTempDir(dir);
    return ExtractVideoFramesResult.parse({ dir, manifestPath, frames: frames.map(frame => frame.path), manifest });
  } catch (error) {
    if (dir) {
      await chmod(dir, 0o700);
      await rm(dir, { recursive: true, force: true });
    }
    throw error;
  } finally { activeCalls--; }
}
