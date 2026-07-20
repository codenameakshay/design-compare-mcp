"""Compare component MOTION between reference and candidate frame sequences.

Loads sequences captured by scripts/capture_frames.mjs and reports each
component's motion energy, temporal rhythm match, and motion score using the
vision_worker.motion library.

Run: worker/.venv/bin/python scripts/motion_score.py [slug ...]
"""

from __future__ import annotations

import glob
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "worker"))
from vision_worker.motion import compare_sequences  # noqa: E402

PAIRS = ROOT / "calibration" / "pairs"


def load(frame_dir: Path, side: str) -> list[np.ndarray]:
    out = []
    for p in sorted(glob.glob(str(frame_dir / f"{side}_*.png"))):
        out.append(np.asarray(Image.open(p).convert("L").resize((206, 108)), dtype=np.float32))
    return out


def main():
    only = sys.argv[1:]
    slugs = sorted(d.parent.name for d in PAIRS.glob("*/frames"))
    slugs = [s for s in slugs if not only or s in only]
    if not slugs:
        print("no frame sequences found (run scripts/capture_frames.mjs first)")
        return
    print(f"{'component':16s} {'ref_E':>7} {'cand_E':>7} {'ratio':>6} {'t-corr':>7} {'motion':>7}")
    for slug in slugs:
        fd = PAIRS / slug / "frames"
        rf, cf = load(fd, "ref"), load(fd, "cand")
        if len(rf) < 2 or len(cf) < 2:
            continue
        r = compare_sequences(rf, cf)
        tc = f"{r['temporal_corr']:+.2f}" if r["temporal_corr"] is not None else "  n/a"
        flag = "" if r["ref_moving"] == r["cand_moving"] else "  <- one side static!"
        print(f"{slug:16s} {r['ref_energy']:7.4f} {r['cand_energy']:7.4f} "
              f"{r['energy_ratio']:6.2f} {tc:>7} {r['motion_score']:6.1f}{flag}")
    print("\nref_E/cand_E = motion energy (mean per-frame change); ratio -> motion_score;")
    print("t-corr = temporal rhythm match (n/a for steady motion with no profile).")


if __name__ == "__main__":
    main()
