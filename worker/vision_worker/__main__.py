"""Persistent stdio JSON-lines worker.

Reads one JSON request per line from stdin and writes one JSON response per
line to stdout. All diagnostics go to stderr so stdout stays a clean protocol
channel for the TS parent process.

Request:   {"id": <int>, "method": <str>, "params": {...}}
Response:  {"id": <int>, "ok": true,  "result": {...}}
       or  {"id": <int>, "ok": false, "error": {"type": <str>, "message": <str>}}

On boot the worker emits one notification line so the parent knows the process
is alive and its stdout pipe is flowing:
           {"event": "ready", "protocol": 1, "pid": <int>, "version": <str>}
"""

from __future__ import annotations

import json
import os
import sys
import traceback

from . import PROTOCOL, __version__


def _log(msg: str) -> None:
    print(f"[vision_worker] {msg}", file=sys.stderr, flush=True)


def _send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def handle_ping(params: dict) -> dict:
    return {
        "pong": True,
        "protocol": PROTOCOL,
        "version": __version__,
        "echo": params,
    }


def handle_compare_designs(params: dict) -> dict:
    """Phase 0 stub. Returns the real result shape with zeroed values so the
    TS layer and host can be wired against the final contract now."""
    mode = params.get("mode", "screen")

    def _sub() -> dict:
        return {"score": 0.0, "reason": "stub — no analysis performed", "measurements": {}}

    return {
        "overall": 0.0,
        "subscores": {
            "layout": _sub(),
            "color": _sub(),
            "content": _sub(),
            "typography": _sub(),
            "spacing": _sub(),
        },
        "cv_findings": [],
        "visuals": [],
        "critique_rubric": (
            "Phase 0 stub — no analysis performed yet. In later phases this "
            "field will instruct the host on how to assemble a prioritized "
            "punch-list from subscores, cv_findings, and the overlay image."
        ),
        "alignment": {"mode": mode, "transform": None, "residual": None, "note": "stub"},
        "stub": True,
    }


HANDLERS = {
    "ping": handle_ping,
    "compare_designs": handle_compare_designs,
}


def main() -> int:
    _send(
        {
            "event": "ready",
            "protocol": PROTOCOL,
            "pid": os.getpid(),
            "version": __version__,
        }
    )
    _log(f"ready (pid={os.getpid()}, python={sys.version.split()[0]})")

    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            _send({"id": None, "ok": False, "error": {"type": "ParseError", "message": str(exc)}})
            continue

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params") or {}

        handler = HANDLERS.get(method)
        if handler is None:
            _send(
                {
                    "id": req_id,
                    "ok": False,
                    "error": {"type": "UnknownMethod", "message": f"unknown method: {method!r}"},
                }
            )
            continue

        try:
            result = handler(params)
            _send({"id": req_id, "ok": True, "result": result})
        except Exception as exc:  # report every handler error back to the client
            _log("handler error:\n" + traceback.format_exc())
            _send(
                {
                    "id": req_id,
                    "ok": False,
                    "error": {"type": type(exc).__name__, "message": str(exc)},
                }
            )

    _log("stdin closed, exiting")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
