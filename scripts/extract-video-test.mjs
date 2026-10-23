import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { chmod, copyFile, mkdir, mkdtemp, readFile, readdir, realpath, rm, stat, symlink, truncate, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import http from "node:http";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { extractVideoFrames, VIDEO_LIMITS } from "../dist/extract-video.js";
import { ExtractVideoFramesInput } from "../dist/schema.js";
import { runVideoProcess } from "../dist/video-process.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const workspace = await realpath(await mkdtemp(path.join(os.tmpdir(), "dcm-extractor-test-")));
const permitted = path.join(workspace, "allowed $; [frames] ' space");
await mkdir(permitted);
const originalEnv = { ...process.env };
process.env.DESIGN_COMPARE_ALLOWED_ROOTS = permitted;
const outputs = [];
let transport;
let client;
let server;

function ffmpeg(args) {
  const result = spawnSync(originalEnv.DESIGN_COMPARE_FFMPEG || "ffmpeg", ["-hide_banner", "-loglevel", "error", "-nostdin", ...args], { encoding: "utf8", timeout: 15_000 });
  assert.equal(result.status, 0, result.stderr || String(result.error));
}

async function extract(args) {
  const result = await extractVideoFrames(args);
  outputs.push(result.dir);
  return result;
}

async function rejectsClean(args, pattern) {
  const before = (await readdir(permitted)).sort();
  await assert.rejects(async () => { const result = await extractVideoFrames(args); outputs.push(result.dir); }, pattern);
  assert.deepEqual((await readdir(permitted)).sort(), before, "partial extraction directory removed");
}

function object(result) {
  assert(!result.isError, JSON.stringify(result.content));
  return JSON.parse(result.content.find(block => block.type === "text").text);
}

function externalReference(data, target) {
  const reference = Buffer.concat([Buffer.alloc(12), Buffer.from(target + "\0")]);
  reference.writeUInt32BE(reference.length);
  reference.write("url ", 4);
  const rewrite = (buffer) => {
    const chunks = [];
    for (let offset = 0; offset < buffer.length;) {
      const size = buffer.readUInt32BE(offset);
      assert(size >= 8 && offset + size <= buffer.length);
      const type = buffer.toString("ascii", offset + 4, offset + 8);
      let payload = buffer.subarray(offset + 8, offset + size);
      if (type === "mdat") payload = Buffer.alloc(payload.length);
      if (["moov", "trak", "mdia", "minf", "dinf"].includes(type)) payload = rewrite(payload);
      if (type === "dref") payload = Buffer.concat([Buffer.from([0, 0, 0, 0, 0, 0, 0, 1]), reference]);
      const header = Buffer.alloc(8);
      header.writeUInt32BE(payload.length + 8);
      header.write(type, 4);
      chunks.push(header, payload);
      offset += size;
    }
    return Buffer.concat(chunks);
  };
  return rewrite(data);
}

try {
  const videoPath = path.join(permitted, "clip $HOME; ' [input].mp4");
  ffmpeg(["-f", "lavfi", "-i", "testsrc2=size=160x96:rate=10:duration=1.2", "-c:v", "mpeg4", "-bf", "2", "-q:v", "2", videoPath]);
  for (const args of [
    {}, { videoPath: "relative.mp4", durationMs: 100 }, { videoPath: "https://example.com/a.mp4", durationMs: 100 },
    { videoPath, durationMs: 0 }, { videoPath, durationMs: 20_001 }, { videoPath, durationMs: 100, startMs: -1 },
    { videoPath, durationMs: 100, fps: 31 }, { videoPath, durationMs: 100, fps: 0 },
    { videoPath, durationMs: 100, fps: 1.5 }, { videoPath, durationMs: Infinity },
    { videoPath, durationMs: NaN }, { videoPath, durationMs: 5000, fps: 30 },
    { videoPath, durationMs: 100, outDir: permitted },
  ]) assert.equal(ExtractVideoFramesInput.safeParse(args).success, false, JSON.stringify(args));
  assert.equal(ExtractVideoFramesInput.parse({ videoPath, durationMs: 1 }).startMs, 0);
  assert.equal(ExtractVideoFramesInput.parse({ videoPath, durationMs: 4000, fps: 30 }).fps, 30);
  const result = await extract({ videoPath, durationMs: 1000, fps: 5 });
  assert.equal(result.manifest.sampling, "complete");
  assert.deepEqual(result.manifest.frames.map(frame => frame.actualMs), [0, 200, 400, 600, 800]);
  assert.deepEqual(result.manifest.samples.map(sample => sample.requestedMs), [0, 200, 400, 600, 800]);
  assert.deepEqual(result.frames, result.manifest.frames.map(frame => frame.path));
  assert(result.frames.every(frame => path.isAbsolute(frame) && frame.startsWith(permitted + path.sep)));
  assert.equal(result.manifest.source.sha256, createHash("sha256").update(await readFile(videoPath)).digest("hex"));
  assert.deepEqual(JSON.parse(await readFile(result.manifestPath, "utf8")), result.manifest);
  assert.match(result.manifest.versions.ffmpeg, /^ffmpeg version/);
  assert.match(result.manifest.versions.ffprobe, /^ffprobe version/);
  assert.equal((await stat(result.dir)).mode & 0o222, 0);
  assert.equal((await stat(result.frames[0])).mode & 0o222, 0);
  const shifted = await extract({ videoPath, startMs: 150, durationMs: 550, fps: 5 });
  assert.deepEqual(shifted.manifest.frames.map(frame => frame.actualMs), [200, 400, 600]);
  const repeated = await extract({ videoPath, durationMs: 1000, fps: 5 });
  assert.notEqual(result.dir, repeated.dir);
  for (let index = 0; index < result.frames.length; index++) assert.deepEqual(await readFile(result.frames[index]), await readFile(repeated.frames[index]));
  const running = [extract({ videoPath, durationMs: 100 }), extract({ videoPath, durationMs: 100 })];
  await assert.rejects(() => extractVideoFrames({ videoPath, durationMs: 100 }), /At most two/);
  const concurrent = await Promise.all(running);
  assert.notEqual(concurrent[0].dir, concurrent[1].dir);
  console.log("PASS strict schema, real CFR/B-frame timestamps, seek, immutable fresh output, concurrency, metacharacters");

  const sparse = path.join(permitted, "sparse.mov");
  ffmpeg(["-f", "lavfi", "-i", "testsrc2=size=160x96:rate=2:duration=2", "-c:v", "mpeg4", sparse]);
  const shared = await extract({ videoPath: sparse, durationMs: 600, fps: 10 });
  assert.equal(shared.manifest.sampling, "sparse");
  assert.equal(shared.frames.length, 2);
  assert.equal(shared.manifest.samples.filter(sample => sample.kind === "shared").length, 4);
  const incomplete = await extract({ videoPath: sparse, startMs: 1000, durationMs: 1000, fps: 10 });
  assert.equal(incomplete.manifest.sampling, "incomplete");
  assert.equal(incomplete.frames.length, 2);
  assert.equal(incomplete.manifest.samples.filter(sample => sample.kind === "unavailable").length, 4);
  await rejectsClean({ videoPath: sparse, startMs: 1700, durationMs: 200 }, /no decodable/);
  await rejectsClean({ videoPath, durationMs: 1300 }, /outside source duration/);
  console.log("PASS sparse/shared source selection and short/incomplete half-open windows");

  const fractional = path.join(permitted, "thirty-fps.mp4");
  ffmpeg(["-f", "lavfi", "-i", "testsrc2=size=160x96:rate=30:duration=0.5", "-c:v", "mpeg4", fractional]);
  const thirty = await extract({ videoPath: fractional, durationMs: 500, fps: 30 });
  assert.equal(thirty.frames.length, 15);
  assert.equal(thirty.manifest.sampling, "complete");
  for (const [index, frame] of thirty.manifest.frames.entries()) assert(Math.abs(frame.actualMs - index * 1000 / 30) < 1e-8);

  const vfr = path.join(permitted, "variable.mp4");
  ffmpeg(["-f", "lavfi", "-i", "testsrc2=size=160x96:rate=10:duration=1.2", "-vf", "select='not(eq(n,2)+eq(n,3)+eq(n,7))'", "-fps_mode", "vfr", "-c:v", "mpeg4", vfr]);
  const variable = await extract({ videoPath: vfr, durationMs: 1000, fps: 5 });
  assert.deepEqual(variable.manifest.frames.map(frame => frame.actualMs), [0, 400, 600, 800]);
  assert.deepEqual(variable.manifest.samples.map(sample => sample.kind), ["selected", "selected", "shared", "selected", "selected"]);
  const rotated = path.join(permitted, "rotated.mov");
  ffmpeg(["-display_rotation", "90", "-i", videoPath, "-c", "copy", rotated]);
  const rotation = await extract({ videoPath: rotated, durationMs: 500, fps: 2 });
  assert.equal(Math.abs(rotation.manifest.source.rotationDegrees), 90);
  assert.equal(rotation.manifest.source.displayWidth, 96);
  assert.equal(rotation.manifest.source.displayHeight, 160);
  const png = await readFile(rotation.frames[0]);
  assert.equal(png.readUInt32BE(16), 96);
  assert.equal(png.readUInt32BE(20), 160);
  const offset = path.join(permitted, "offset.mp4");
  ffmpeg(["-i", videoPath, "-c", "copy", "-output_ts_offset", "2", offset]);
  const normalized = await extract({ videoPath: offset, startMs: 150, durationMs: 550, fps: 5 });
  assert(normalized.manifest.source.firstPts > 0);
  assert.deepEqual(normalized.manifest.frames.map(frame => frame.actualMs), [200, 400, 600]);
  console.log("PASS VFR uses real PTS, portrait rotation, nonzero source timestamp normalization");

  const outside = path.join(workspace, "outside.mp4");
  await copyFile(videoPath, outside);
  const escape = path.join(permitted, "symlink.mp4");
  await symlink(outside, escape);
  await rejectsClean({ videoPath: outside, durationMs: 100 }, /outside DESIGN_COMPARE_ALLOWED_ROOTS/);
  await rejectsClean({ videoPath: escape, durationMs: 100 }, /outside DESIGN_COMPARE_ALLOWED_ROOTS/);
  await rejectsClean({ videoPath: permitted, durationMs: 100 }, /regular local file/);
  await rejectsClean({ videoPath: path.join(permitted, "missing.mp4"), durationMs: 100 }, /ENOENT/);
  const corrupt = path.join(permitted, "corrupt.mp4");
  await writeFile(corrupt, "not video");
  await rejectsClean({ videoPath: corrupt, durationMs: 100 }, /MP4|MOV|failed/);
  const playlist = path.join(permitted, "playlist.mp4");
  await writeFile(playlist, "#EXTM3U\nhttp://127.0.0.1:1/video.ts\n");
  await rejectsClean({ videoPath: playlist, durationMs: 100 }, /MP4|MOV|failed/);
  const audio = path.join(permitted, "audio.mp4");
  ffmpeg(["-f", "lavfi", "-i", "sine=frequency=1000:duration=1", "-c:a", "aac", audio]);
  await rejectsClean({ videoPath: audio, durationMs: 100 }, /supported video stream/);
  const huge = path.join(permitted, "huge.mp4");
  await writeFile(huge, "");
  await truncate(huge, VIDEO_LIMITS.inputBytes + 1);
  await rejectsClean({ videoPath: huge, durationMs: 100 }, /512 MiB/);
  const oversized = path.join(permitted, "oversized.mov");
  ffmpeg(["-f", "lavfi", "-i", "color=red:size=4100x4000:rate=1:duration=1", "-c:v", "png", "-threads", "1", oversized]);
  await rejectsClean({ videoPath: oversized, durationMs: 100 }, /failed|megapixels|supported video/);
  const truncated = path.join(permitted, "truncated.mp4");
  ffmpeg(["-i", videoPath, "-c", "copy", "-movflags", "+faststart", truncated]);
  await truncate(truncated, Math.floor((await stat(truncated)).size * 0.6));
  await rejectsClean({ videoPath: truncated, durationMs: 1000, fps: 5 }, /failed|supported video/);
  for (const name of ["DESIGN_COMPARE_FFMPEG", "DESIGN_COMPARE_FFPROBE"]) {
    process.env[name] = path.join(workspace, "missing-binary");
    await rejectsClean({ videoPath, durationMs: 100 }, /Install FFmpeg with ffprobe/);
    if (originalEnv[name]) process.env[name] = originalEnv[name];
    else delete process.env[name];
  }
  console.log("PASS allowlist, symlink escape, corrupt/playlist/audio-only/missing input, size cap, missing dependencies, cleanup");
  if (process.getuid?.() !== 0) {
    await chmod(permitted, 0o555);
    try { await rejectsClean({ videoPath, durationMs: 100 }, /No permitted writable output root/); }
    finally { await chmod(permitted, 0o700); }
  }

  let requests = 0;
  server = http.createServer((_req, response) => { requests++; response.writeHead(200); response.end("external data must not be fetched"); });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const networkReference = path.join(permitted, "network-reference.mov");
  const localReference = path.join(permitted, "local-reference.mov");
  const media = await readFile(videoPath);
  await writeFile(networkReference, externalReference(media, `http://127.0.0.1:${server.address().port}/external.mov`));
  await writeFile(localReference, externalReference(media, outside));
  await rejectsClean({ videoPath: networkReference, durationMs: 100 }, /External|failed|supported video/);
  await rejectsClean({ videoPath: localReference, durationMs: 100 }, /External|failed|supported video/);
  assert.equal(requests, 0);
  console.log("PASS external network/local MOV reference regression, no HTTP requests");

  await assert.rejects(runVideoProcess({ binary: process.execPath, args: ["-e", "setInterval(()=>{},1000)"], deadline: Date.now() + 100, maxOutputBytes: 1000 }), /deadline/);
  await assert.rejects(runVideoProcess({ binary: process.execPath, args: ["-e", "process.stdout.write('x'.repeat(10000))"], deadline: Date.now() + 1000, maxOutputBytes: 100 }), /byte limit/);
  await assert.rejects(runVideoProcess({ binary: process.execPath, args: ["-e", "process.stderr.write('x'.repeat(5000000))"], deadline: Date.now() + 1000, maxOutputBytes: 10_000_000 }), /4 MiB/);
  console.log("PASS subprocess timeout and output bounds");

  client = new Client({ name: "extract-video-test", version: "1" });
  transport = new StdioClientTransport({ command: process.execPath, args: [path.join(ROOT, "dist/index.js")], cwd: workspace,
    env: { ...originalEnv, DESIGN_COMPARE_ALLOWED_ROOTS: permitted }, stderr: "inherit" });
  await client.connect(transport);
  const tool = (await client.listTools()).tools.find(tool => tool.name === "extract_video_frames");
  assert(tool);
  assert.equal(tool.inputSchema.additionalProperties, false);
  const extracted = object(await client.callTool({ name: "extract_video_frames", arguments: { videoPath, durationMs: 1000, fps: 5 } }));
  outputs.push(extracted.dir);
  const still = object(await client.callTool({ name: "compare_designs", arguments: { reference: extracted.frames[0], candidate: extracted.frames[0], returnVisuals: false } }));
  assert.equal(still.stub, false);
  assert.equal(typeof still.overall, "number");
  const motion = object(await client.callTool({ name: "compare_motion", arguments: { reference: extracted.frames, candidate: extracted.dir, returnVisuals: false } }));
  assert.equal(motion.motion_status, "compared");
  assert(motion.ref_energy > 0);
  const staticVideo = path.join(permitted, "static.mp4");
  ffmpeg(["-f", "lavfi", "-i", "color=white:size=160x96:rate=5:duration=1,drawgrid=width=20:height=20:color=black:thickness=3", "-c:v", "mpeg4", staticVideo]);
  const staticFrames = object(await client.callTool({ name: "extract_video_frames", arguments: { videoPath: staticVideo, durationMs: 1000, fps: 5 } }));
  outputs.push(staticFrames.dir);
  assert.equal(staticFrames.frames.length, 5, "identical pixels at distinct PTS remain separate frames");
  const staticMotion = object(await client.callTool({ name: "compare_motion", arguments: { reference: staticFrames.frames, candidate: staticFrames.frames, returnVisuals: false } }));
  assert.equal(staticMotion.motion_status, "static");
  assert.equal(staticMotion.motion_score, null);
  for (const arguments_ of [{ videoPath, durationMs: 100, extra: true }, { videoPath, durationMs: 5000, fps: 30 }]) {
    const invalid = await client.callTool({ name: "extract_video_frames", arguments: arguments_ });
    assert.equal(invalid.isError, true);
  }
  const denied = await client.callTool({ name: "extract_video_frames", arguments: { videoPath: outside, durationMs: 100 } });
  assert.equal(denied.isError, true);
  assert.equal(JSON.parse(denied.content[0].text).type, "DisallowedPath");
  console.log("PASS MCP extraction -> image and motion comparison under Python allowlist from unrelated cwd; static motion remains null");
  const captured = await client.callTool({ name: "capture_frames", arguments: {
    url: `http://127.0.0.1:${server.address().port}/capture`, frames: 1, waitMs: 0,
    viewport: { width: 160, height: 96 }, outDir: path.join(permitted, "browser-capture"),
  } });
  if (captured.isError && /Chrome|Chromium|DESIGN_COMPARE_CHROME/.test(JSON.stringify(captured.content))) {
    console.log("SKIP capture_frames response check: Chrome unavailable");
  } else {
    const capture = object(captured);
    assert.equal(capture.frames.length, 1);
    assert(path.isAbsolute(capture.frames[0]));
    assert.equal((await stat(capture.frames[0])).isFile(), true);
    console.log("PASS capture_frames exposes ordered frame paths");
  }
  await import("./extract-video-lifecycle-test.mjs");
  console.log("ALL EXTRACTOR CHECKS PASSED");
} finally {
  await client?.close().catch(() => {});
  await transport?.close().catch(() => {});
  if (server) await new Promise(resolve => server.close(resolve));
  for (const dir of outputs) await chmod(dir, 0o700).catch(() => {});
  for (const name of ["DESIGN_COMPARE_ALLOWED_ROOTS", "DESIGN_COMPARE_FFMPEG", "DESIGN_COMPARE_FFPROBE"]) {
    if (originalEnv[name] !== undefined) process.env[name] = originalEnv[name];
    else delete process.env[name];
  }
  await rm(workspace, { recursive: true, force: true });
}
