import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs/promises";
import { chmod, mkdtemp, readdir, realpath, rm, truncate, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { mock } from "node:test";
import { syncBuiltinESMExports } from "node:module";
import { fileURLToPath } from "node:url";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { extractVideoFrames } from "../dist/extract-video.js";
import { runVideoProcess } from "../dist/video-process.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const workspace = await realpath(await mkdtemp(path.join(os.tmpdir(), "dcm-video-lifecycle-")));
const originalEnv = { ...process.env };
const processes = new Set();
const transports = new Set();
process.env.DESIGN_COMPARE_ALLOWED_ROOTS = workspace;

function alive(pid) {
  try { process.kill(pid, 0); return true; }
  catch (error) { if (error.code === "ESRCH") return false; throw error; }
}

async function until(read, message, timeoutMs = 5000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const result = await read();
    if (result) return result;
    await delay(10);
  }
  assert.fail(message);
}

async function bundles() {
  return (await readdir(workspace)).filter(name => name.startsWith("dcm-video-")).sort();
}

async function connect(ffmpeg) {
  const client = new Client({ name: "extractor-lifecycle", version: "1" });
  const transport = new StdioClientTransport({ command: process.execPath, args: [path.join(ROOT, "dist/index.js")], cwd: workspace,
    env: { ...originalEnv, DESIGN_COMPARE_ALLOWED_ROOTS: workspace, DESIGN_COMPARE_FFMPEG: ffmpeg }, stderr: "inherit" });
  transports.add(transport);
  await client.connect(transport);
  processes.add(transport.pid);
  return { client, transport };
}

try {
  const videoPath = path.join(workspace, "clip.mp4");
  const ffmpeg = originalEnv.DESIGN_COMPARE_FFMPEG || "ffmpeg";
  const generated = spawnSync(ffmpeg, ["-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=160x96:rate=10:duration=1", "-c:v", "mpeg4", videoPath], { encoding: "utf8", timeout: 15_000 });
  assert.equal(generated.status, 0, generated.stderr);
  const args = { videoPath, durationMs: 1000, fps: 5 };

  const alreadyAborted = AbortSignal.abort(new Error("cancelled before start"));
  await assert.rejects(extractVideoFrames(args, alreadyAborted), /cancelled before start/);
  assert.deepEqual(await bundles(), []);

  const large = path.join(workspace, "copy.mp4");
  await writeFile(large, "");
  await truncate(large, 128 * 1024 * 1024);
  for (const phase of ["copy", "export"]) {
    const controller = new AbortController();
    let writtenBytes = 0;
    if (phase === "copy") {
      const open = fs.open;
      mock.method(fs, "open", async (...args) => {
        const handle = await open(...args);
        if (path.basename(String(args[0])) === "source.snapshot") {
          const write = handle.write.bind(handle);
          mock.method(handle, "write", async (...args) => {
            const result = await write(...args);
            writtenBytes += result.bytesWritten;
            controller.abort(new Error("cancelled during copy"));
            return result;
          });
        }
        return handle;
      });
    } else {
      const write = fs.writeFile;
      mock.method(fs, "writeFile", async (...args) => {
        await write(...args);
        if (path.basename(String(args[0])) === "frame_000.png") {
          writtenBytes += args[1].length;
          controller.abort(new Error("cancelled during export"));
        }
      });
    }
    syncBuiltinESMExports();
    try {
      await assert.rejects(extractVideoFrames({ ...args, videoPath: phase === "copy" ? large : videoPath }, controller.signal), /cancelled during/);
      assert(writtenBytes > 0, `${phase} cancellation happens after real bytes reach disk`);
      if (phase === "copy") assert(writtenBytes < 128 * 1024 * 1024, "copy stops before reading the full source");
      assert.deepEqual(await bundles(), [], `${phase} cancellation removes private snapshot and partial exports`);
    } finally { mock.restoreAll(); syncBuiltinESMExports(); }
  }
  console.log("PASS pre-abort, snapshot-copy and frame-export cancellation remove partial bundles");

  const controller = new AbortController();
  let pid;
  let output = "";
  const running = runVideoProcess({ binary: process.execPath, args: ["-e", "process.stderr.write(String(process.pid)+'\\n'); process.on('SIGTERM',()=>{}); setInterval(()=>{},1000)"],
    deadline: Date.now() + 10_000, maxOutputBytes: 1000, signal: controller.signal,
    onStderr(text) {
      output += text;
      if (output.includes("\n")) {
        pid = Number(output.trim());
        processes.add(pid);
        controller.abort(new Error("cancelled subprocess"));
      }
    } });
  await assert.rejects(running, /cancelled subprocess/);
  assert.equal(Number.isInteger(pid), true);
  assert.equal(alive(pid), false, "subprocess promise settles only after the child is reaped");
  console.log("PASS subprocess cancellation reaps a SIGTERM-resistant child before settlement");

  const wrapper = path.join(workspace, "controlled-ffmpeg.mjs");
  await writeFile(wrapper, `#!${process.execPath}
import { spawnSync } from 'node:child_process';
import { writeFileSync, existsSync } from 'node:fs';
const args = process.argv.slice(2);
if (args.includes('-version') || existsSync(${JSON.stringify(path.join(workspace, "allow-decode"))})) {
  const result = spawnSync(${JSON.stringify(ffmpeg)}, args, { stdio: 'inherit' });
  process.exit(result.status ?? 1);
}
writeFileSync(${JSON.stringify(workspace)} + '/decoder-' + process.pid, String(process.pid));
process.on('SIGTERM', () => {});
setInterval(() => {}, 1000);
`, { mode: 0o700 });
  const decoderPids = async () => (await readdir(workspace)).filter(name => name.startsWith("decoder-")).map(name => Number(name.slice(8)));
  const started = async count => until(async () => {
    const pids = await decoderPids();
    pids.forEach(pid => processes.add(pid));
    return pids.length === count && pids;
  }, `expected ${count} active decoders`);

  const { client, transport } = await connect(wrapper);
  const controllers = [new AbortController(), new AbortController()];
  const pending = controllers.map(controller => client.callTool({ name: "extract_video_frames", arguments: args }, undefined, { signal: controller.signal }).catch(error => error));
  const pids = await started(2);
  const partial = await bundles();
  assert.equal(partial.length, 2);
  for (const name of partial) assert.deepEqual(await readdir(path.join(workspace, name)), ["source.snapshot"]);
  controllers.forEach(controller => controller.abort());
  for (const result of await Promise.all(pending)) assert.match(result.message, /abort/i);
  await until(async () => pids.every(pid => !alive(pid)) && (await bundles()).length === 0, "cancelled MCP requests must reap decoders and remove private snapshots");
  await writeFile(path.join(workspace, "allow-decode"), "");
  const replacements = await Promise.all(controllers.map(() => client.callTool({ name: "extract_video_frames", arguments: args })));
  for (const result of replacements) {
    assert.notEqual(result.isError, true, JSON.stringify(result));
    const extracted = JSON.parse(result.content[0].text);
    assert.equal(extracted.frames.length, 5, "both extraction slots become reusable after cleanup");
    assert.equal((await readdir(extracted.dir)).includes("source.snapshot"), false);
  }
  await client.close();
  await transport.close();
  transports.delete(transport);
  console.log("PASS MCP cancellation reaps both decoders, removes snapshots and restores both slots");

  await rm(path.join(workspace, "allow-decode"));
  for (const reason of ["SIGTERM", "stdin-eof"]) {
    const before = await bundles();
    const beforePids = (await decoderPids()).length;
    const proc = spawn(process.execPath, [path.join(ROOT, "dist/index.js")], { cwd: workspace,
      env: { ...originalEnv, DESIGN_COMPARE_ALLOWED_ROOTS: workspace, DESIGN_COMPARE_FFMPEG: wrapper }, stdio: ["pipe", "pipe", "pipe"] });
    processes.add(proc.pid);
    let diagnostic = "";
    proc.stderr.on("data", chunk => { diagnostic += chunk; });
    const closed = new Promise(resolve => proc.once("close", (code, signal) => resolve({ code, signal })));
    proc.stdout.resume();
    await until(() => diagnostic.includes("server ready on stdio"), "shutdown-test server must become ready", 30_000);
    await until(() => /ready \(pid=\d+, python=/.test(diagnostic), "shutdown-test worker must report its PID");
    const workerPid = Number(/ready \(pid=(\d+), python=/.exec(diagnostic)?.[1]);
    assert.equal(Number.isInteger(workerPid), true, diagnostic);
    processes.add(workerPid);
    proc.stdin.write(JSON.stringify({ jsonrpc: "2.0", id: 1, method: "initialize", params: { protocolVersion: "2024-11-05", capabilities: {}, clientInfo: { name: "lifecycle", version: "1" } } }) + "\n");
    proc.stdin.write(JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" }) + "\n");
    for (const id of [2, 3]) proc.stdin.write(JSON.stringify({ jsonrpc: "2.0", id, method: "tools/call", params: { name: "extract_video_frames", arguments: args } }) + "\n");
    const activePids = (await started(beforePids + 2)).filter(alive);
    assert.equal(activePids.length, 2);
    const partial = (await bundles()).filter(name => !before.includes(name));
    assert.equal(partial.length, 2);
    for (const name of partial) assert.deepEqual(await readdir(path.join(workspace, name)), ["source.snapshot"]);
    if (reason === "SIGTERM") proc.kill("SIGTERM");
    else proc.stdin.end();
    await until(() => !alive(proc.pid), `server must exit after extraction cleanup: ${diagnostic}`);
    assert.deepEqual(await closed, { code: 0, signal: null });
    assert.equal(alive(workerPid), false, "server exit must not leave a Python worker orphan");
    assert.deepEqual(await bundles(), before, "server exit must not leave private snapshots or cancelled bundles");
    for (const pid of activePids) assert.equal(alive(pid), false, "server exit must not leave a decoder orphan");
    console.log(`PASS ${reason} waits for both active extractions to reap children and delete private snapshots`);
  }
  console.log("ALL EXTRACTOR LIFECYCLE CHECKS PASSED");
} finally {
  for (const transport of transports) await transport.close().catch(() => {});
  for (const pid of processes) if (alive(pid)) process.kill(pid, "SIGKILL");
  for (const name of await bundles()) await chmod(path.join(workspace, name), 0o700).catch(() => {});
  if (originalEnv.DESIGN_COMPARE_ALLOWED_ROOTS === undefined) delete process.env.DESIGN_COMPARE_ALLOWED_ROOTS;
  else process.env.DESIGN_COMPARE_ALLOWED_ROOTS = originalEnv.DESIGN_COMPARE_ALLOWED_ROOTS;
  await rm(workspace, { recursive: true, force: true });
}
