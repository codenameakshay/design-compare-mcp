"""Repeatable leak + latency probe for the vision pipeline.

Runs many comparisons in one long-lived process (as the worker does) and reports
RSS growth and per-call latency. Run with the venv interpreter:
    worker/.venv/bin/python scripts/stress.py [iterations]
"""

from __future__ import annotations

import gc
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "worker"))

from calibration.synthetic import card_screen  # noqa: E402
from vision_worker.pipeline import compare_arrays  # noqa: E402


def rss_mb() -> float:
    return int(subprocess.check_output(["ps", "-o", "rss=", "-p", str(os.getpid())])) / 1024


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    ref = card_screen()
    cand = card_screen(header=(120, 40, 60), btn=(220, 60, 60))

    compare_arrays(ref, cand, return_visuals=True)  # warm up
    gc.collect()
    start = rss_mb()
    print(f"leak test: {n} comparisons (start RSS {start:.1f} MB)")
    for i in range(n):
        compare_arrays(ref, cand, return_visuals=True)
        if (i + 1) % 100 == 0:
            gc.collect()
            print(f"  after {i + 1:4d}: RSS={rss_mb():.1f} MB")
    gc.collect()
    print(f"  growth over {n} calls: {rss_mb() - start:+.1f} MB")

    for vis in (False, True):
        t = time.time()
        m = 40
        for _ in range(m):
            compare_arrays(ref, cand, return_visuals=vis)
        print(f"latency visuals={vis!s:5s}: {1000 * (time.time() - t) / m:.1f} ms/call")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
