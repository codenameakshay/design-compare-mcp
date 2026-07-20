"""Image loading helpers with input-safety guards."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

# Bound decode memory from hostile/huge inputs. We downscale to the canonical
# width (768) for processing anyway, so materializing beyond this is wasted work
# and a DoS vector (a ~178MP image can allocate hundreds of MB before analysis).
MAX_PIXELS = 40_000_000  # ~40 MP
MAX_DIM = 12_000  # px on any single side

# Optional path allowlist for untrusted/multi-tenant hosts. Colon-separated roots
# in DESIGN_COMPARE_ALLOWED_ROOTS; when unset (default), any local path is allowed
# (single-user local-trust assumption).
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


def load_rgb(path: str) -> np.ndarray:
    """Load an image as a contiguous HxWx3 uint8 RGB array.

    Honors EXIF orientation, enforces a decode-size cap before pixels are
    materialized, and (optionally) restricts reads to an allowlist of roots.
    """
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"image not found: {path}")
    _check_allowed(p)

    with Image.open(p) as im:
        # im.size comes from the header, before pixel decode — check first.
        w, h = im.size
        if w * h > MAX_PIXELS or max(w, h) > MAX_DIM:
            raise ImageTooLargeError(
                f"image {w}x{h} exceeds limits "
                f"({MAX_PIXELS} px total / {MAX_DIM} px per side)"
            )
        im = ImageOps.exif_transpose(im)
        arr = np.asarray(im.convert("RGB"))
    return np.ascontiguousarray(arr)
