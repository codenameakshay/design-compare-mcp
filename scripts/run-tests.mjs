import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..");
const PYTHON = existsSync(path.join(ROOT, "worker", ".venv", "bin", "python"))
  ? path.join(ROOT, "worker", ".venv", "bin", "python")
  : "python3";

function run(cmd, args) {
  const result = spawnSync(cmd, args, { cwd: ROOT, stdio: "inherit" });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

run("npm", ["run", "build"]);
run("node", ["scripts/extract-video-test.mjs"]);

for (const test of [
  "worker/tests/test_pipeline.py",
  "worker/tests/test_calibration.py",
  "worker/tests/test_robustness.py",
  "worker/tests/test_motion.py",
  "worker/tests/test_color_stability.py",
  "worker/tests/test_reliability.py",
]) {
  run(PYTHON, [test]);
}

run("npm", ["run", "smoke"]);
run("node", ["scripts/reliability-smoke.mjs"]);
run(PYTHON, ["scripts/reliability-benchmark.py", "--self-test-runner"]);
run("node", ["scripts/render-reliability-test.mjs", "docs/reliability/runs/final"]);
run("npm", ["run", "resilience"]);
