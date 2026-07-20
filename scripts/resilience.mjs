// Resilience test for the worker supervisor: auto-restart after a crash,
// survival of worker-reported errors, and correct handling of concurrent
// requests. Run after `npm run build`:  node scripts/resilience.mjs
import { PythonWorker } from "../dist/worker-client.js";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function assert(cond, msg) {
  if (!cond) throw new Error("ASSERT FAILED: " + msg);
}

const worker = new PythonWorker();
try {
  await worker.start();
  const first = await worker.request("ping", { message: "a" });
  assert(first.pong === true, "initial ping works");
  const pid1 = worker.pid;
  assert(typeof pid1 === "number", "worker has a pid");
  console.log(`booted, pid=${pid1}`);

  // --- 1. Auto-restart after a hard kill ---
  process.kill(pid1, "SIGKILL");
  await sleep(300); // let the exit handler run
  const afterKill = await worker.request("ping", { message: "b" });
  assert(afterKill.pong === true, "ping succeeds after the worker was killed");
  const pid2 = worker.pid;
  assert(typeof pid2 === "number" && pid2 !== pid1, "a NEW worker was spawned");
  console.log(`auto-restarted, pid=${pid2} (was ${pid1}) ✓`);

  // --- 2. Worker-reported error does not kill the worker ---
  let errored = false;
  try {
    await worker.request("compare_designs", {
      reference: "/no/such/ref.png",
      candidate: "/no/such/cand.png",
    });
  } catch {
    errored = true;
  }
  assert(errored, "bad-path compare rejects with an error");
  const stillAlive = await worker.request("ping", { message: "c" });
  assert(stillAlive.pong === true, "worker still responsive after an error");
  assert(worker.pid === pid2, "no restart needed for a handled error");
  console.log("survived a worker-reported error without restarting ✓");

  // --- 3. Concurrent request burst demuxes correctly ---
  const burst = await Promise.all(
    Array.from({ length: 25 }, (_, i) => worker.request("ping", { message: String(i) })),
  );
  assert(
    burst.every((r, i) => r.pong === true && r.echo.message === String(i)),
    "all concurrent responses matched their requests",
  );
  console.log("25 concurrent requests demuxed correctly ✓");

  await worker.stop();
  console.log("\nRESILIENCE CHECKS PASSED ✅");
  process.exit(0);
} catch (err) {
  console.error("\nRESILIENCE TEST FAILED ❌\n", err);
  await worker.stop().catch(() => {});
  process.exit(1);
}
