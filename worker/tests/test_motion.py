"""Unit tests for the motion comparison library (no captured frames needed)."""

from __future__ import annotations

import base64
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
    # Both animate identically -> high motion score, both flagged moving.
    r = compare_sequences(moving_seq(), moving_seq())
    print("both moving:", {k: r[k] for k in ("ref_energy", "cand_energy", "motion_score")})
    assert r["ref_moving"] and r["cand_moving"]
    assert r["motion_score"] > 90, r["motion_score"]

    # One animates, one static -> hard motion miss (score 0), asymmetric flags.
    r2 = compare_sequences(moving_seq(), static_seq())
    print("moving vs static:", {k: r2[k] for k in ("ref_moving", "cand_moving", "motion_score")})
    assert r2["ref_moving"] and not r2["cand_moving"]
    assert r2["motion_score"] == 0.0

    # Both static -> treated as matching (no motion on either side).
    r3 = compare_sequences(static_seq(), static_seq())
    assert not r3["ref_moving"] and not r3["cand_moving"]
    assert r3["motion_score"] == 100.0, r3["motion_score"]

    # Half the animation speed -> lower but nonzero energy ratio.
    r4 = compare_sequences(moving_seq(step=4), moving_seq(step=2))
    print("speed mismatch:", {k: r4[k] for k in ("energy_ratio", "motion_score")})
    assert 0.0 < r4["motion_score"] < 90, r4["motion_score"]

    # End-to-end compare_motion: load frames from directories + build the visual.
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

    # Also accepts an explicit list of frame paths.
    paths = sorted(str(p) for p in Path(d1).glob("*.png"))
    r6 = compare_motion(paths, paths, return_visuals=False)
    assert r6["motion_score"] == 100.0, r6["motion_score"]

    print("\nMotion library + compare_motion checks PASSED ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
