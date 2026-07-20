import { spawn, type ChildProcess } from "node:child_process";
import { createInterface, type Interface } from "node:readline";
import { once } from "node:events";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
// Both dist/worker-client.js and src/worker-client.ts sit one level below the
// repo root, so `..` resolves the repo root in built and dev (tsx) runs alike.
const REPO_ROOT = path.resolve(HERE, "..");
const WORKER_CWD = path.join(REPO_ROOT, "worker");

/** Prefer the project venv interpreter if it exists, else system python3. */
function defaultPython(): string {
  const candidates = [
    path.join(WORKER_CWD, ".venv", "bin", "python"),
    path.join(WORKER_CWD, ".venv", "Scripts", "python.exe"),
  ];
  for (const c of candidates) {
    if (fs.existsSync(c)) return c;
  }
  return "python3";
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

interface Pending {
  resolve: (value: unknown) => void;
  reject: (err: Error) => void;
  timer: NodeJS.Timeout;
}

export interface WorkerError {
  type: string;
  message: string;
}

export interface WorkerOptions {
  pythonBin?: string;
  requestTimeoutMs?: number;
  bootTimeoutMs?: number;
}

/**
 * Supervises a single long-lived Python vision worker and multiplexes
 * request/response pairs over its stdio using newline-delimited JSON.
 *
 * The worker stays resident so heavy imports load once. It is self-healing: if
 * the worker dies, the next request lazily respawns it (with backoff), so one
 * crash costs at most a single failed call instead of bricking the session.
 */
export class PythonWorker {
  private proc: ChildProcess | null = null;
  private rl: Interface | null = null;
  private nextId = 1;
  private readonly pending = new Map<number, Pending>();
  private ready = false;
  private stopped = false;
  private starting: Promise<void> | null = null;
  private bootReject: ((e: Error) => void) | null = null;
  private failureStreak = 0;
  private readonly pythonBin: string;
  private readonly requestTimeoutMs: number;
  private readonly bootTimeoutMs: number;

  constructor(opts: WorkerOptions = {}) {
    this.pythonBin =
      opts.pythonBin ?? process.env.DESIGN_COMPARE_PYTHON ?? defaultPython();
    this.requestTimeoutMs = opts.requestTimeoutMs ?? 30_000;
    this.bootTimeoutMs = opts.bootTimeoutMs ?? 15_000;
  }

  /** PID of the live worker, if any (diagnostics / tests). */
  get pid(): number | undefined {
    return this.proc?.pid;
  }

  /** Idempotent: ensures a live, ready worker, coalescing concurrent callers. */
  async start(): Promise<void> {
    if (this.stopped) throw new Error("vision worker has been stopped");
    if (this.proc && this.ready) return;
    if (!this.starting) {
      this.starting = this.boot().finally(() => {
        this.starting = null;
      });
    }
    return this.starting;
  }

  private async boot(): Promise<void> {
    // Exponential backoff throttles crash/boot loops (reset on a real response).
    if (this.failureStreak > 0) {
      await sleep(Math.min(5000, 100 * 2 ** Math.min(this.failureStreak - 1, 6)));
    }
    if (this.stopped) throw new Error("vision worker has been stopped");
    try {
      await this.spawnWorker();
    } catch (e) {
      this.failureStreak++;
      throw e;
    }
  }

  private spawnWorker(): Promise<void> {
    const proc = spawn(this.pythonBin, ["-m", "vision_worker"], {
      cwd: WORKER_CWD,
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
      stdio: ["pipe", "pipe", "pipe"],
    });
    this.proc = proc;
    this.ready = false;

    // Worker stderr is diagnostics only — forward to our stderr, never stdout
    // (our stdout is the MCP protocol channel to the host).
    proc.stderr?.setEncoding("utf8");
    proc.stderr?.on("data", (chunk: string) => process.stderr.write(chunk));

    proc.on("exit", (code, signal) => {
      const wasReady = this.ready;
      this.ready = false;
      this.proc = null;
      this.rl?.close();
      this.rl = null;

      const err = Object.assign(
        new Error(`vision worker exited (code=${code}, signal=${signal})`),
        { workerCrashed: true },
      );
      for (const p of this.pending.values()) {
        clearTimeout(p.timer);
        p.reject(err);
      }
      this.pending.clear();

      // Fail an in-flight boot immediately instead of waiting for bootTimer
      // (e.g. a Python import error that exits before emitting `ready`).
      this.bootReject?.(err);

      // Count unexpected deaths of a healthy worker toward the backoff streak.
      if (!this.stopped && wasReady) this.failureStreak++;
    });

    return new Promise<void>((resolve, reject) => {
      const cleanup = () => {
        clearTimeout(bootTimer);
        this.bootReject = null;
      };
      const settleReject = (e: Error) => {
        cleanup();
        reject(e);
      };

      const bootTimer = setTimeout(() => {
        settleReject(new Error("vision worker did not become ready in time"));
        this.proc?.kill("SIGKILL");
      }, this.bootTimeoutMs);

      this.bootReject = settleReject;
      proc.once("error", (e) => settleReject(e as Error));

      const rl = createInterface({ input: proc.stdout! });
      this.rl = rl;
      rl.on("line", (line: string) => {
        const trimmed = line.trim();
        if (!trimmed) return;

        let msg: Record<string, unknown>;
        try {
          msg = JSON.parse(trimmed);
        } catch {
          process.stderr.write(
            `[worker-client] non-JSON line from worker: ${trimmed.slice(0, 200)}\n`,
          );
          return;
        }

        if (msg.event === "ready") {
          this.ready = true;
          cleanup();
          resolve();
          return;
        }
        this.dispatch(msg);
      });
    });
  }

  private dispatch(msg: Record<string, unknown>): void {
    const id = msg.id;
    if (typeof id !== "number") {
      process.stderr.write(
        "[worker-client] dropping message without numeric id\n",
      );
      return;
    }
    // A well-formed response proves the worker is alive and doing work.
    this.failureStreak = 0;

    const p = this.pending.get(id);
    if (!p) return;
    this.pending.delete(id);
    clearTimeout(p.timer);

    if (msg.ok) {
      p.resolve(msg.result);
    } else {
      const werr = msg.error as WorkerError | undefined;
      p.reject(
        Object.assign(new Error(werr?.message ?? "worker error"), {
          workerError: werr,
        }),
      );
    }
  }

  async request<T = unknown>(
    method: string,
    params: Record<string, unknown> = {},
  ): Promise<T> {
    try {
      return await this.send<T>(method, params);
    } catch (e) {
      // A crash of a previously-healthy worker → retry once on a fresh worker.
      // Comparisons are idempotent, so a single replay is safe. Timeouts and
      // worker-reported errors are not retried.
      if ((e as { workerCrashed?: boolean })?.workerCrashed && !this.stopped) {
        return this.send<T>(method, params);
      }
      throw e;
    }
  }

  private async send<T>(
    method: string,
    params: Record<string, unknown>,
  ): Promise<T> {
    await this.start();
    const proc = this.proc;
    if (!proc || !this.ready) throw new Error("vision worker not available");

    const id = this.nextId++;
    const payload = JSON.stringify({ id, method, params }) + "\n";

    return new Promise<T>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(
          new Error(
            `worker request '${method}' timed out after ${this.requestTimeoutMs}ms`,
          ),
        );
      }, this.requestTimeoutMs);

      this.pending.set(id, {
        resolve: resolve as (v: unknown) => void,
        reject,
        timer,
      });

      proc.stdin!.write(payload, (err) => {
        if (err) {
          clearTimeout(timer);
          this.pending.delete(id);
          reject(err);
        }
      });
    });
  }

  async stop(): Promise<void> {
    this.stopped = true;
    const proc = this.proc;
    if (!proc) return;
    // Already exited (or exiting): nothing to wait on — avoids hanging on a
    // `once('exit')` that will never fire.
    if (proc.exitCode !== null || proc.signalCode !== null) return;

    proc.stdin?.end();
    const killTimer = setTimeout(() => proc.kill("SIGKILL"), 2000);
    try {
      await once(proc, "exit");
    } catch {
      /* already gone */
    } finally {
      clearTimeout(killTimer);
    }
  }
}
