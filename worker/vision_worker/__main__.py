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

# --- STDOUT ISOLATION (must run before importing heavy libs) ---------------
# stdout is the framed JSON-lines protocol channel. Reserve the real stdout fd
# for framed responses only, then repoint fd 1 (and sys.stdout) at stderr so any
# stray print/native-library write to stdout can never corrupt the protocol.
try:
    _PROTOCOL_OUT = os.fdopen(os.dup(1), "w", buffering=1)
    sys.stdout.flush()
    os.dup2(2, 1)  # fd 1 -> stderr
except OSError:  # pragma: no cover - non-fd stdout (unusual); fall back
    _PROTOCOL_OUT = sys.__stdout__

from . import PROTOCOL, __version__  # noqa: E402
from .pipeline import compare as _compare  # noqa: E402


def _log(msg: str) -> None:
    print(f"[vision_worker] {msg}", file=sys.stderr, flush=True)


def _send(obj: dict) -> None:
    _PROTOCOL_OUT.write(json.dumps(obj) + "\n")
    _PROTOCOL_OUT.flush()


def handle_ping(params: dict) -> dict:
    return {
        "pong": True,
        "protocol": PROTOCOL,
        "version": __version__,
        "echo": params,
    }


def handle_compare_designs(params: dict) -> dict:
    return _compare(
        reference=params.get("reference", ""),
        candidate=params.get("candidate", ""),
        mode=params.get("mode", "screen"),
        ignore_regions=params.get("ignoreRegions"),
        return_visuals=params.get("returnVisuals", True),
        weights=params.get("weights"),
    )


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
