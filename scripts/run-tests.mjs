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

for (const test of [
  "worker/tests/test_pipeline.py",
  "worker/tests/test_calibration.py",
  "worker/tests/test_robustness.py",
  "worker/tests/test_motion.py",
]) {
  run(PYTHON, [test]);
}

run("npm", ["run", "smoke"]);
run("npm", ["run", "resilience"]);
