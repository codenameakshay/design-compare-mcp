// Lifecycle test: the server must not outlive its MCP host.
//
// Regression guard for the orphan leak — 552 stray processes (276 node + 276
// python) accumulated over ~4 days because the server never noticed its host
// had gone away. Run after `npm run build`:  node scripts/lifecycle.mjs
import { spawn, execSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SERVER = path.join(REPO_ROOT, "dist", "index.js");

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function assert(cond, msg) {
  if (!cond) throw new Error("ASSERT FAILED: " + msg);
}

const alive = (pid) => {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
};

/** Descendant pids of `pid` (one level is enough: node -> python worker). */
function childPids(pid) {
  return execSync(`pgrep -P ${pid} || true`, { encoding: "utf8" })
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean)
    .map(Number);
}

/** Boot a server over stdio and wait for it to report ready on stderr. */
async function bootServer() {
  const proc = spawn(process.execPath, [SERVER], {
    cwd: REPO_ROOT,
    stdio: ["pipe", "pipe", "pipe"],
  });
  proc.stderr.setEncoding("utf8");

  await new Promise((resolve, reject) => {
    const timer = setTimeout(
      () => reject(new Error("server did not become ready in 30s")),
      30_000,
    );
    proc.stderr.on("data", (chunk) => {
      if (chunk.includes("server ready on stdio")) {
        clearTimeout(timer);
        resolve();
      }
    });
    proc.once("exit", (code) => {
      clearTimeout(timer);
      reject(new Error(`server exited during boot (code=${code})`));
    });
  });

  // The python worker boots before the transport connects, so it exists by now.
  const workers = childPids(proc.pid);
  assert(workers.length === 1, `expected 1 python worker, saw ${workers.length}`);
  return { proc, workerPid: workers[0] };
}

/** Wait up to `ms` for `pid` to disappear. */
async function waitForExit(pid, ms) {
  const deadline = Date.now() + ms;
  while (Date.now() < deadline) {
    if (!alive(pid)) return true;
    await sleep(100);
  }
  return false;
}

try {
  // --- 1. Host goes away (stdin EOF) -> server and worker both exit ---
  // This is what actually happens when an MCP host quits: it does NOT signal
  // the server, it just closes the pipes. The server is reparented to init.
  {
    const { proc, workerPid } = await bootServer();
    console.log(`booted, server=${proc.pid} worker=${workerPid}`);

    proc.stdin.end(); // host disconnects

    const serverGone = await waitForExit(proc.pid, 10_000);
    assert(serverGone, "server exited after its host closed stdin");
    const workerGone = await waitForExit(workerPid, 5_000);
    assert(workerGone, "python worker exited with the server");
    console.log("stdin EOF -> server and worker both exited ✓");
  }

  // --- 2. SIGTERM -> server and worker both exit ---
  {
    const { proc, workerPid } = await bootServer();
    process.kill(proc.pid, "SIGTERM");

    const serverGone = await waitForExit(proc.pid, 10_000);
    assert(serverGone, "server exited on SIGTERM");
    const workerGone = await waitForExit(workerPid, 5_000);
    assert(workerGone, "python worker exited on SIGTERM");
    console.log("SIGTERM -> server and worker both exited ✓");
  }

  // --- 3. Host is SIGKILLed -> no orphans left behind ---
  // The end-to-end shape of the real leak: a host process spawns the server and
  // is then killed outright, with no chance to clean up after itself.
  {
    const host = spawn(
      process.execPath,
      [
        "-e",
        `const {spawn}=require('node:child_process');
         const c=spawn(process.execPath,[${JSON.stringify(SERVER)}],{stdio:['pipe','pipe','inherit']});
         console.log(c.pid); setInterval(()=>{},1000);`,
      ],
      { cwd: REPO_ROOT, stdio: ["ignore", "pipe", "inherit"] },
    );
    host.stdout.setEncoding("utf8");
    const serverPid = Number(
      await new Promise((r) => host.stdout.once("data", (d) => r(d.trim()))),
    );
    await sleep(12_000); // let the python worker finish booting
    const workers = childPids(serverPid);
    assert(workers.length === 1, `expected 1 worker under the server, saw ${workers.length}`);

    process.kill(host.pid, "SIGKILL"); // host dies without cleaning up

    const serverGone = await waitForExit(serverPid, 10_000);
    assert(serverGone, "server did not survive its host being SIGKILLed");
    const workerGone = await waitForExit(workers[0], 5_000);
    assert(workerGone, "python worker did not outlive the killed host");
    console.log("host SIGKILL -> no orphaned server or worker ✓");
  }

  console.log("\nLIFECYCLE CHECKS PASSED ✅");
  process.exit(0);
} catch (err) {
  console.error("\nLIFECYCLE TEST FAILED ❌\n", err);
  process.exit(1);
}
