"""Image loading helpers with input-safety guards."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

_FRAME_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
MAX_FRAMES = 240
FRAME_WORK_SIZE = (240, 135)

MAX_PIXELS = 40_000_000
MAX_DIM = 12_000

_ALLOWED_ROOTS = [
    Path(p).expanduser().resolve()
    for p in os.environ.get("DESIGN_COMPARE_ALLOWED_ROOTS", "").split(os.pathsep)
    if p
]


class ImageTooLargeError(ValueError):
    """Raised when an input image exceeds the decode-size limits."""


def _check_allowed(p: Path) -> None:
    if not _ALLOWED_ROOTS:
        return
    rp = p.resolve()
    if not any(rp == root or root in rp.parents for root in _ALLOWED_ROOTS):
        raise PermissionError(f"path is outside the allowed roots: {p}")


def _unique_resolved(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for fp in paths:
        key = str(Path(fp).expanduser().resolve())
        if key in seen:
            continue
        seen.add(key)
        out.append(fp)
    return out


def _dir_frame_paths(p: Path) -> list[str]:
    found = [
        str(child)
        for child in p.iterdir()
        if child.is_file() and child.suffix.lower() in _FRAME_SUFFIXES
    ]
    return sorted(found)


def load_rgb(path: str) -> np.ndarray:
    """Load an image as a contiguous HxWx3 uint8 RGB array.

    Honors EXIF orientation, enforces a decode-size cap before pixels are
    materialized, and (optionally) restricts reads to an allowlist of roots.
    """
    p = Path(path).expanduser()
    _check_allowed(p)
    if not p.exists():
        raise FileNotFoundError(f"image not found: {path}")

    with Image.open(p) as im:
        w, h = im.size
        if w * h > MAX_PIXELS or max(w, h) > MAX_DIM:
            raise ImageTooLargeError(
                f"image {w}x{h} exceeds limits "
                f"({MAX_PIXELS} px total / {MAX_DIM} px per side)"
            )
        im = ImageOps.exif_transpose(im)
        arr = np.asarray(im.convert("RGB"))
    return np.ascontiguousarray(arr)


def load_frame_sequence(source, max_frames: int | None = None) -> list[np.ndarray]:
    """Load an ordered grayscale frame sequence for motion comparison.

    `source` is either a directory (its image files, sorted by name) or an
    explicit list of frame image paths. Frames are converted to grayscale and
    resized to a fixed working size so within-sequence frame diffs are valid.
    """
    if isinstance(source, (list, tuple)):
        paths = [str(p) for p in source]
    else:
        p = Path(str(source)).expanduser()
        _check_allowed(p)
        if not p.exists():
            raise FileNotFoundError(f"frame source not found: {source}")
        if not p.is_dir():
            raise ValueError(f"frame source must be a directory or a list of paths: {source}")
        paths = _dir_frame_paths(p)

    paths = _unique_resolved(paths)
    if not paths:
        raise ValueError(f"no frames found in {source}")
    cap = min(max_frames or MAX_FRAMES, MAX_FRAMES)
    paths = paths[:cap]
    if len(paths) < 2:
        raise ValueError(f"need at least 2 frames, got {len(paths)}")

    frames = []
    for fp in paths:
        fpp = Path(fp).expanduser()
        _check_allowed(fpp)
        if not fpp.exists():
            raise FileNotFoundError(f"frame not found: {fp}")
        with Image.open(fpp) as im:
            w, h = im.size
            if w * h > MAX_PIXELS or max(w, h) > MAX_DIM:
                raise ImageTooLargeError(
                    f"image {w}x{h} exceeds limits "
                    f"({MAX_PIXELS} px total / {MAX_DIM} px per side)"
                )
            im = im.convert("L").resize(FRAME_WORK_SIZE)
            frames.append(np.asarray(im, dtype=np.float32))
    return frames
