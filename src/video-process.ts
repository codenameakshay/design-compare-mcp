import { spawn } from "node:child_process";

export class VideoExtractionError extends Error {
  constructor(readonly code: "InvalidVideo" | "DisallowedPath" | "UnavailableWindow" | "ResourceLimit" | "MissingDecoder" | "DecodeFailure", message: string) {
    super(message);
  }
}

export function runVideoProcess(options: {
  binary: string;
  args: string[];
  deadline: number;
  maxOutputBytes: number;
  signal?: AbortSignal;
  onStderr?: (text: string) => void;
}): Promise<{ stdout: Buffer; stderr: string }> {
  return new Promise((resolve, reject) => {
    options.signal?.throwIfAborted();
    const proc = spawn(options.binary, options.args, { shell: false, stdio: ["ignore", "pipe", "pipe"] });
    const stdout: Buffer[] = [];
    const stderr: Buffer[] = [];
    let bytes = 0;
    let stderrBytes = 0;
    let failure: Error | undefined;
    const fail = (error: Error) => {
      failure ??= error;
      proc.kill("SIGKILL");
    };
    const abort = () => fail(options.signal?.reason instanceof Error ? options.signal.reason : new Error("Video extraction cancelled"));
    options.signal?.addEventListener("abort", abort, { once: true });
    const timer = setTimeout(() => fail(new VideoExtractionError("ResourceLimit", "Video processing exceeded its deadline")), Math.max(1, options.deadline - Date.now()));
    proc.on("error", error => {
      failure = new VideoExtractionError("MissingDecoder", `Cannot run ${options.binary}: ${error.message}. Install FFmpeg with ffprobe and put both on PATH, or set DESIGN_COMPARE_FFMPEG / DESIGN_COMPARE_FFPROBE.`);
    });
    const collect = (chunk: Buffer, destination: Buffer[]) => {
      bytes += chunk.length;
      if (bytes > options.maxOutputBytes) {
        fail(new VideoExtractionError("ResourceLimit", "Video subprocess output exceeded its byte limit"));
        return false;
      }
      destination.push(chunk);
      return true;
    };
    proc.stdout.on("data", (chunk: Buffer) => collect(chunk, stdout));
    proc.stderr.on("data", (chunk: Buffer) => {
      stderrBytes += chunk.length;
      if (stderrBytes > 4 * 1024 * 1024) {
        fail(new VideoExtractionError("ResourceLimit", "Video subprocess diagnostics exceeded 4 MiB"));
        return;
      }
      if (!collect(chunk, stderr)) return;
      try { options.onStderr?.(chunk.toString("utf8")); }
      catch (error) { fail(error instanceof Error ? error : new Error(String(error))); }
    });
    proc.on("close", code => {
      clearTimeout(timer);
      options.signal?.removeEventListener("abort", abort);
      if (failure) reject(failure);
      else if (code !== 0) reject(new VideoExtractionError("DecodeFailure", `${options.binary} failed (${code}): ${Buffer.concat(stderr).toString("utf8").slice(-2000)}`));
      else resolve({ stdout: Buffer.concat(stdout), stderr: Buffer.concat(stderr).toString("utf8") });
    });
  });
}
