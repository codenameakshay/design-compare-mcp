"""Static measurement caveats and decoded-input comparison identity, version 1."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import platform
import re
import struct
from pathlib import Path

import cv2
import numpy as np

from .normalize import CANON_WIDTH


def canonical_json(value) -> bytes:
    def clean(item):
        if isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError("provenance numbers must be finite")
            return 0 if item == 0 else item
        if isinstance(item, dict):
            return {key: clean(val) for key, val in item.items()}
        if isinstance(item, (list, tuple)):
            return [clean(val) for val in item]
        return item

    return json.dumps(clean(value), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def validate_context(context) -> dict | None:
    if context is None:
        return None
    if not isinstance(context, dict) or set(context) != {"scopeId", "protocolKey"}:
        raise ValueError("comparisonContext must contain only scopeId and protocolKey")
    scope, protocol = context["scopeId"], context["protocolKey"]
    # Zod's string bounds count UTF-16 code units, not Python code points.
    if not isinstance(scope, str) or not 1 <= len(scope.encode("utf-16-le", "surrogatepass")) // 2 <= 128:
        raise ValueError("comparisonContext.scopeId must contain 1 to 128 UTF-16 code units")
    try:
        scope = scope.encode("utf-16-le", "surrogatepass").decode("utf-16-le")
    except UnicodeDecodeError:
        raise ValueError("comparisonContext.scopeId must contain valid Unicode without lone surrogates") from None
    if not isinstance(protocol, str) or re.fullmatch(r"[0-9a-f]{64}", protocol) is None:
        raise ValueError("comparisonContext.protocolKey must be lowercase SHA256 hex")
    return {"scopeId": scope, "protocolKey": protocol}


def canonical_ignores(boxes) -> list[list[float]]:
    normalized = set()
    for box in boxes if boxes is not None else []:
        if not isinstance(box, (list, tuple)) or len(box) != 4:
            raise ValueError("ignore regions must be four finite numbers")
        vals = tuple(float(v) for v in box)
        if not all(math.isfinite(v) for v in vals):
            raise ValueError("ignore regions must be four finite numbers")
        normalized.add(tuple(0.0 if v == 0 else v for v in vals))
    # Keep unclipped, zero and negative-size declarations. Rasterization remains legacy.
    return [list(box) for box in sorted(normalized)]


def scoring_source_digest(root: Path | None = None) -> str:
    """Hash the production worker package, not tests/docs or Git state.

    Conservatively includes motion and visual diagnostics: editing either also
    splits static comparison keys, even if static scoring is unchanged.
    """
    root = root or Path(__file__).resolve().parent
    digest = hashlib.sha256(b"dcm-scoring-source-v1\0")
    for source in sorted(root.rglob("*.py")):
        name = source.relative_to(root).as_posix().encode("utf-8")
        contents = source.read_bytes()
        digest.update(struct.pack(">Q", len(name)) + name)
        digest.update(struct.pack(">Q", len(contents)) + contents)
    return "sha256:" + digest.hexdigest()


def _runtime_identity() -> dict:
    versions = {"python": platform.python_version(), "numpy": np.__version__,
                "opencv": cv2.__version__}
    for package in ("Pillow", "scikit-image", "scipy", "scikit-learn"):
        versions[package] = importlib.metadata.version(package)
    return {"engine_revision": scoring_source_digest(), "runtime_versions": versions}


_ENGINE_IDENTITY = _runtime_identity()


def pixel_identity(rgb: np.ndarray) -> dict:
    if not isinstance(rgb, np.ndarray) or rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("comparison inputs must be HxWx3 uint8 RGB arrays")
    height, width = rgb.shape[:2]
    if not height or not width:
        raise ValueError("comparison inputs must have nonzero dimensions")
    digest = hashlib.sha256(b"dcm-rgb-v1\0" + struct.pack(">QQ", width, height))
    digest.update(np.ascontiguousarray(rgb).data)
    return {"rgb_sha256": digest.hexdigest(), "width": width, "height": height}


def make_provenance(ref_rgb, cand_rgb, *, mode, preset, weights, ignore_regions,
                    comparison_context) -> dict:
    settings = {
        **_ENGINE_IDENTITY,
        "runtime_versions": dict(_ENGINE_IDENTITY["runtime_versions"]),
        "canonical_width": CANON_WIDTH,
        "normalization_policy": "independent-width-modal-bottom-pad-v1",
        "alignment_policy": "ecc-translation-guards-v1",
        "ignore_policy": "reference-boxes-per-image-modal-fill-v1",
        "mode": mode,
        "preset": preset or "default",
        "weights": weights,
        "ignore_regions": canonical_ignores(ignore_regions),
        "comparison_context": validate_context(comparison_context),
    }
    inputs = {"reference": pixel_identity(ref_rgb), "candidate": pixel_identity(cand_rgb)}
    comparison_key = hashlib.sha256(b"dcm-compare-v1\0" + canonical_json({
        "reference": inputs["reference"], "settings": settings,
    })).hexdigest()
    run_key = hashlib.sha256(b"dcm-run-v1\0" + canonical_json({
        "comparison_key": comparison_key, "candidate": inputs["candidate"],
    })).hexdigest()
    return {"version": 1, "comparison_key": comparison_key, "run_key": run_key,
            "inputs": inputs, "settings": settings}


def capture_stats(rgb: np.ndarray) -> dict:
    # OpenCV accumulates in float64 without a full-size RGB float intermediate.
    _, channel_std = cv2.meanStdDev(rgb)
    for channel in range(3):
        if abs(float(channel_std[channel, 0]) - 2.0) <= 1e-6:
            # E[x²]-E[x]² cancellation can put an exact 2.0 below the policy
            # boundary. Exact uint8 moments resolve it without rounding or a
            # changed threshold; row chunks bound bincount's integer temporary.
            counts = np.zeros(256, dtype=np.int64)
            for row in range(0, rgb.shape[0], 64):
                counts += np.bincount(rgb[row:row+64, :, channel].reshape(-1), minlength=256)
            n = rgb.shape[0] * rgb.shape[1]
            total = sum(value * int(count) for value, count in enumerate(counts))
            squares = sum(value * value * int(count) for value, count in enumerate(counts))
            channel_std[channel, 0] = math.sqrt((n * squares - total * total) / (n * n))
    rgb_std = float(channel_std.max())
    _, gray_std = cv2.meanStdDev(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY))
    return {"rgb_stddev_max": rgb_std,
            "gray_stddev": float(gray_std[0, 0]),
            "near_uniform": rgb_std < 2.0}


def make_diagnostics(ref_rgb, cand_rgb, pair, alignment, warp, subscores,
                     identity_score) -> dict:
    capture = {"reference": capture_stats(ref_rgb), "candidate": capture_stats(cand_rgb)}
    issues = [{"code": "near_uniform_input", "side": side}
              for side, stats in capture.items() if stats["near_uniform"]]
    if (alignment["outcome"] == "identity_fallback"
            and not np.array_equal(ref_rgb, cand_rgb)):
        issues.append({"code": "alignment_unresolved"})
    if warp is not None and max(abs(float(warp[0, 2])), abs(float(warp[1, 2]))) >= 1.0:
        issues.append({"code": "translation_applied"})
    if pair.aspect_mismatch > 0.02:
        issues.append({"code": "aspect_mismatch"})
    ignored = float(pair.ignore.mask.mean())
    if ignored > 0:
        issues.append({"code": "mask_fill_semantics"})
        if pair.ref.pad_color != pair.cand.pad_color:
            issues.append({"code": "mask_fill_colors_differ"})
    if ignored == 1:
        issues.append({"code": "empty_compare_scope"})
    issues.extend({"code": "metric_failed", "metric": name}
                  for name, sub in subscores.items() if sub["status"] == "failed")
    return {
        "version": 1,
        "status": "inconclusive" if ignored == 1 else "review" if issues else "ok",
        "issues": issues,
        "capture": capture,
        "scope": {"ignored_fraction": ignored, "compared_fraction": 1 - ignored},
        "layout_identity_score": identity_score,
    }
