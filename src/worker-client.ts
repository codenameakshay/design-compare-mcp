import { spawn, type ChildProcess } from "node:child_process";
import { createInterface, type Interface } from "node:readline";
import { once } from "node:events";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
// Both dist/worker-client.js and src/worker-client.ts sit one level below the
// repo root, so `..` resolves the repo root in built and dev (tsx) runs alike.
const REPO_ROOT = path.resolve(HERE, "..");
const WORKER_CWD = path.join(REPO_ROOT, "worker");

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
 * Manages a single long-lived Python vision worker and multiplexes
 * request/response pairs over its stdio using newline-delimited JSON.
 * The worker stays resident so heavy imports (opencv/torch, later) load once.
 */
export class PythonWorker {
  private proc: ChildProcess | null = null;
  private rl: Interface | null = null;
  private nextId = 1;
  private readonly pending = new Map<number, Pending>();
  private ready = false;
  private readonly pythonBin: string;
  private readonly requestTimeoutMs: number;
  private readonly bootTimeoutMs: number;

  constructor(opts: WorkerOptions = {}) {
    this.pythonBin =
      opts.pythonBin ?? process.env.DESIGN_COMPARE_PYTHON ?? "python3";
    this.requestTimeoutMs = opts.requestTimeoutMs ?? 30_000;
    this.bootTimeoutMs = opts.bootTimeoutMs ?? 15_000;
  }

  async start(): Promise<void> {
    if (this.proc) return;

    const proc = spawn(this.pythonBin, ["-m", "vision_worker"], {
      cwd: WORKER_CWD,
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
      stdio: ["pipe", "pipe", "pipe"],
    });
    this.proc = proc;

    // Worker stderr is diagnostics only — forward to our stderr, never stdout
    // (our stdout is the MCP protocol channel to the host).
    proc.stderr?.setEncoding("utf8");
    proc.stderr?.on("data", (chunk: string) => process.stderr.write(chunk));

    proc.on("exit", (code, signal) => {
      this.ready = false;
      const err = new Error(
        `vision worker exited (code=${code}, signal=${signal})`,
      );
      for (const p of this.pending.values()) {
        clearTimeout(p.timer);
        p.reject(err);
      }
      this.pending.clear();
      this.proc = null;
      this.rl?.close();
      this.rl = null;
    });

    await new Promise<void>((resolve, reject) => {
      const bootTimer = setTimeout(() => {
        if (!this.ready)
          reject(new Error("vision worker did not become ready in time"));
      }, this.bootTimeoutMs);

      proc.once("error", (e) => {
        clearTimeout(bootTimer);
        reject(e);
      });

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
            `[worker-client] non-JSON line from worker: ${trimmed}\n`,
          );
          return;
        }

        if (msg.event === "ready") {
          this.ready = true;
          clearTimeout(bootTimer);
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
        `[worker-client] dropping message without numeric id: ${JSON.stringify(msg)}\n`,
      );
      return;
    }
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
    if (!this.proc || !this.ready) throw new Error("vision worker not started");
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

      this.proc!.stdin!.write(payload, (err) => {
        if (err) {
          clearTimeout(timer);
          this.pending.delete(id);
          reject(err);
        }
      });
    });
  }

  async stop(): Promise<void> {
    const proc = this.proc;
    if (!proc) return;
    proc.stdin?.end();
    const exited = once(proc, "exit");
    const killTimer = setTimeout(() => proc.kill("SIGKILL"), 2000);
    try {
      await exited;
    } finally {
      clearTimeout(killTimer);
    }
  }
}
