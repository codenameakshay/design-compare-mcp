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


def positioned_seq(positions):
    frames = []
    for x in positions:
        f = np.zeros((50, 100), np.float32)
        f[20:30, x : x + 8] = 255.0
        frames.append(f)
    return frames


def test_energy_match_does_not_imply_timing_match():
    ref = positioned_seq([0, 4, 4, 8, 8, 12, 12, 16, 16])
    cand = positioned_seq([0, 0, 4, 4, 8, 8, 12, 12, 16])
    result = compare_sequences(ref, cand)
    assert result["motion_score"] == 100.0, result
    assert result["motion_energy_score"] == 100.0, result
    assert result["motion_score_meaning"] == "motion_energy_similarity_only", result
    assert math.isclose(result["temporal_corr"], -1.0), result
    timing = result["timing_diagnostics"]
    assert timing["status"] == "inconclusive", timing
    assert timing["reason"] == "cadence_unknown", timing
    assert timing["score"] is None, timing
    assert timing["cadence_verified"] is False, timing
    assert timing["sampled_profile"]["status"] == "compared", timing
    assert timing["sampled_profile"]["basis"] == "frame_index", timing
    assert math.isclose(timing["sampled_profile"]["correlation"], -1.0), timing
    assert "differ" in timing["recommendation"], timing
    assert "timestamps" in timing["recommendation"], timing


def test_unequal_lengths_do_not_compare_a_truncated_prefix():
    ref = positioned_seq([0, 4, 4, 8, 8])
    cand = positioned_seq([0, 4, 4, 8, 8, 12, 12])
    for reference, candidate in ((ref, cand), (cand, ref)):
        result = compare_sequences(reference, candidate)
        assert result["motion_score"] == 100.0, result
        assert result["temporal_corr"] is None, result
        assert result["motion_energy_score"] == 100.0, result
        timing = result["timing_diagnostics"]
        assert timing["reason"] == "unequal_length", timing
        assert timing["status"] == "inconclusive", timing
        assert timing["score"] is None, timing
        assert timing["sampled_profile"] == {
            "status": "inconclusive", "reason": "unequal_length", "correlation": None,
        }, timing
        assert "equal-length" in timing["recommendation"], timing


def test_matching_sampled_profiles_still_have_unknown_cadence():
    frames = positioned_seq([0, 4, 4, 8, 8])
    result = compare_sequences(frames, frames)
    assert result["motion_energy_score"] == 100.0, result
    assert math.isclose(result["temporal_corr"], 1.0), result
    timing = result["timing_diagnostics"]
    assert timing["status"] == "inconclusive", timing
    assert timing["reason"] == "cadence_unknown", timing
    assert timing["score"] is None, timing
    assert timing["cadence_verified"] is False, timing
    assert timing["sampled_profile"]["status"] == "compared", timing
    assert "not proof" in timing["recommendation"], timing


def test_steady_and_short_motion_have_no_rhythm_evidence():
    steady = moving_seq()
    varying = positioned_seq([0, 4, 4, 8, 8, 12, 12, 16])
    for reference, candidate, score in (
        (steady, steady, 100.0),
        (steady, varying, 57.1),
        (varying, steady, 57.1),
    ):
        result = compare_sequences(reference, candidate)
        assert result["motion_energy_score"] == score, result
        assert result["temporal_corr"] is None, result
        timing = result["timing_diagnostics"]
        assert timing["status"] == "inconclusive", timing
        assert timing["reason"] == "steady_motion", timing
        assert timing["score"] is None, timing
        assert timing["sampled_profile"] == {
            "status": "inconclusive", "reason": "steady_motion", "correlation": None,
        }, timing
        assert "constant" in timing["recommendation"], timing

    short = compare_sequences(steady[:2], steady[:2])
    assert short["motion_energy_score"] == 100.0, short
    assert short["temporal_corr"] is None, short
    assert short["timing_diagnostics"]["reason"] == "insufficient_samples", short
    assert short["timing_diagnostics"]["score"] is None, short


def test_static_and_unreliable_captures_remain_inconclusive():
    pulsing = positioned_seq([0, 4, 4, 8, 8])
    blank = [np.full((50, 100), value, np.float32) for value in (0, 40, 40, 80, 80)]
    cases = (
        (static_seq(), static_seq(), "static", None, "both_static"),
        (pulsing, static_seq(5), "compared", 0.0, "motion_presence_mismatch"),
        (static_seq(5), pulsing, "compared", 0.0, "motion_presence_mismatch"),
        (blank, blank, "capture_unreliable", None, "capture_unreliable"),
        (blank, pulsing, "capture_unreliable", None, "capture_unreliable"),
        (pulsing, blank, "capture_unreliable", None, "capture_unreliable"),
    )
    for reference, candidate, status, score, reason in cases:
        result = compare_sequences(reference, candidate)
        assert result["motion_status"] == status, result
        assert result["motion_score"] == score, result
        assert result["motion_energy_score"] == score, result
        assert result["motion_score_meaning"] == "motion_energy_similarity_only", result
        assert result["temporal_corr"] is None, result
        timing = result["timing_diagnostics"]
        assert timing["status"] == "inconclusive", timing
        assert timing["reason"] == reason, timing
        assert timing["score"] is None, timing
        assert timing["cadence_verified"] is False, timing
        assert timing["sampled_profile"] == {
            "status": "inconclusive", "reason": reason, "correlation": None,
        }, timing
        assert "timestamps" in timing["recommendation"], timing
        json.dumps(result, allow_nan=False)


def main() -> int:
    test_energy_match_does_not_imply_timing_match()
    test_unequal_lengths_do_not_compare_a_truncated_prefix()
    test_matching_sampled_profiles_still_have_unknown_cadence()
    test_steady_and_short_motion_have_no_rhythm_evidence()
    test_static_and_unreliable_captures_remain_inconclusive()
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

    with tempfile.TemporaryDirectory() as temp_root:
        def write_seq(frames, name):
            directory = Path(temp_root) / name
            directory.mkdir()
            for i, f in enumerate(frames):
                Image.fromarray(f.astype("uint8")).save(directory / f"f_{i:02d}.png")
            return str(directory)

        d1 = write_seq(moving_seq(), "reference")
        d2 = write_seq(moving_seq(), "candidate")
        r5 = compare_motion(d1, d2, return_visuals=True)
        print("compare_motion(dirs):", {k: r5[k] for k in ("motion_score", "frames")})
        assert r5["motion_score"] == 100.0 and r5["frames"]["reference"] == 8
        assert r5["motion_energy_score"] == 100.0, r5["motion_energy_score"]
        assert r5["timing_diagnostics"]["status"] == "inconclusive", r5["timing_diagnostics"]
        assert r5["timing_diagnostics"]["score"] is None, r5["timing_diagnostics"]
        assert r5["timing_diagnostics"]["cadence_verified"] is False, r5["timing_diagnostics"]
        assert r5["visuals"][0]["name"] == "motion_signature"
        assert base64.b64decode(r5["visuals"][0]["base64"])[:8] == PNG_MAGIC

        paths = sorted(str(p) for p in Path(d1).glob("*.png"))
        r6 = compare_motion(paths, paths, return_visuals=False)
        assert r6["motion_score"] == 100.0, r6["motion_score"]

    print("\nMotion library + compare_motion checks PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
