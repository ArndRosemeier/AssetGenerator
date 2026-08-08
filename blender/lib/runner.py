"""Entrypoint harness for scripts executed by `blender --background --python`.

Blender's stdout is full of unrelated noise, so every entrypoint communicates
through a single JSON report file. Failures are never swallowed: the exception
and its traceback land in the report and the process exits non-zero.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from collections.abc import Callable, Mapping
from pathlib import Path

from blender.lib.report import Report, format_report

Handler = Callable[[Mapping[str, object]], Report]


def _script_args() -> list[str]:
    if "--" not in sys.argv:
        raise SystemExit("Entrypoint must be invoked with arguments after '--'")
    return sys.argv[sys.argv.index("--") + 1 :]


def execute(command: str, handler: Handler) -> None:
    parser = argparse.ArgumentParser(prog=command)
    parser.add_argument("--payload", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    args = parser.parse_args(_script_args())

    payload_raw = json.loads(args.payload.read_text(encoding="utf-8"))
    if not isinstance(payload_raw, dict):
        raise SystemExit("Payload must be a JSON object")

    try:
        report = handler(payload_raw)
    except BaseException as exc:  # noqa: BLE001 - reported verbatim, never masked
        report = {
            "ok": False,
            "command": command,
            "errors": [f"{type(exc).__name__}: {exc}"],
            "traceback": traceback.format_exc(),
        }

    args.result.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("=== asset-lab report ===")
    print(format_report(report))
    sys.exit(0 if report.get("ok") else 1)
