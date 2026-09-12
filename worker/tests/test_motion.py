from __future__ import annotations

import base64
import json
import math
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vision_worker.motion import compare_sequences  # noqa: E402
from vision_worker.pipeline import compare_motion  # noqa: E402

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def moving_seq(n=8, step=4):
    frames = []
    for i in range(n):
        f = np.zeros((50, 100), np.float32)
        x = (i * step) % 90
        f[20:30, x : x + 8] = 255.0
        frames.append(f)
    return frames


def static_seq(n=8):
    f = np.zeros((50, 100), np.float32)
    f[20:30, 10:18] = 255.0
    return [f.copy() for _ in range(n)]


def main() -> int:
    r = compare_sequences(moving_seq(), moving_seq())
    print("both moving:", {k: r[k] for k in ("ref_energy", "cand_energy", "motion_score")})
    assert r["ref_moving"] and r["cand_moving"]
    assert r["motion_score"] > 90, r["motion_score"]

    r2 = compare_sequences(moving_seq(), static_seq())
    print("moving vs static:", {k: r2[k] for k in ("ref_moving", "cand_moving", "motion_score")})
    assert r2["ref_moving"] and not r2["cand_moving"]
    assert r2["motion_score"] == 0.0

    r3 = compare_sequences(static_seq(), static_seq())
    assert not r3["ref_moving"] and not r3["cand_moving"]
    assert r3["motion_status"] == "static", r3
    assert r3["motion_score"] is None, r3["motion_score"]

    blank = [np.zeros((50, 100), np.float32) for _ in range(8)]
    r_blank = compare_sequences(blank, blank)
    assert r_blank["motion_status"] == "capture_unreliable", r_blank
    assert r_blank["motion_score"] is None, r_blank["motion_score"]
    near = [np.full((50, 100), 11.0, np.float32) for _ in range(8)]
    r_near = compare_sequences(near, moving_seq())
    assert r_near["motion_status"] == "capture_unreliable"
    assert r_near["motion_score"] is None

    assert r2["motion_status"] == "compared"

    def steady_moving(n=8):
        frames = []
        for i in range(n):
            f = np.zeros((50, 100), np.float32)
            f[10:20, 8 + i : 16 + i] = 255.0
            frames.append(f)
        return frames

    r_steady = compare_sequences(steady_moving(), steady_moving())
    assert r_steady["temporal_corr"] is None, r_steady["temporal_corr"]
    for row in (r, r2, r3, r_blank, r_steady):
        tc = row["temporal_corr"]
        assert tc is None or (isinstance(tc, (int, float)) and math.isfinite(tc)), tc
        json.dumps(row, allow_nan=False)

    r4 = compare_sequences(moving_seq(step=4), moving_seq(step=2))
    print("speed mismatch:", {k: r4[k] for k in ("energy_ratio", "motion_score")})
    assert 0.0 < r4["motion_score"] < 90, r4["motion_score"]

    def write_seq(frames):
        d = tempfile.mkdtemp()
        for i, f in enumerate(frames):
            Image.fromarray(f.astype("uint8")).save(f"{d}/f_{i:02d}.png")
        return d

    d1, d2 = write_seq(moving_seq()), write_seq(moving_seq())
    r5 = compare_motion(d1, d2, return_visuals=True)
    print("compare_motion(dirs):", {k: r5[k] for k in ("motion_score", "frames")})
    assert r5["motion_score"] > 90 and r5["frames"]["reference"] == 8
    assert r5["visuals"][0]["name"] == "motion_signature"
    assert base64.b64decode(r5["visuals"][0]["base64"])[:8] == PNG_MAGIC

    paths = sorted(str(p) for p in Path(d1).glob("*.png"))
    r6 = compare_motion(paths, paths, return_visuals=False)
    assert r6["motion_score"] == 100.0, r6["motion_score"]

    print("\nMotion library + compare_motion checks PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
