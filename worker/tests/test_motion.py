"""Unit tests for the motion comparison library (no captured frames needed)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vision_worker.motion import compare_sequences  # noqa: E402


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

    print("\nMotion library checks PASSED ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
