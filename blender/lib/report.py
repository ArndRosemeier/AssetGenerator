"""The JSON contract between headless Blender and the orchestrating CLI.

Stdlib-only: imported by both `tools/ag.py` and code running inside Blender.
"""

from __future__ import annotations

from typing import Literal, TypedDict

Severity = Literal["error", "warning"]


class CheckResult(TypedDict):
    name: str
    ok: bool
    severity: Severity
    detail: str


class MeshStats(TypedDict):
    objects: int
    vertices: int
    triangles: int
    materials: int
    uv_layers: int
    dimensions_m: list[float]


class Report(TypedDict, total=False):
    ok: bool
    command: str
    asset_id: str
    generator: str
    outputs: dict[str, str]
    stats: MeshStats | None
    roundtrip: MeshStats | None
    checks: list[CheckResult]
    errors: list[str]
    traceback: str


def check(name: str, ok: bool, detail: str, severity: Severity = "error") -> CheckResult:
    return {"name": name, "ok": ok, "severity": severity, "detail": detail}


def failed_checks(checks: list[CheckResult]) -> list[CheckResult]:
    return [c for c in checks if not c["ok"] and c["severity"] == "error"]


def format_report(report: Report) -> str:
    """Human/agent readable rendering of a report."""
    lines: list[str] = []
    status = "PASS" if report.get("ok") else "FAIL"
    asset_id = report.get("asset_id", "?")
    lines.append(f"[{status}] {report.get('command', '?')}  asset={asset_id}")

    stats = report.get("stats")
    if stats is not None:
        dims = ", ".join(f"{value:.3f}" for value in stats["dimensions_m"])
        lines.append(
            f"  geometry: {stats['triangles']} tris, {stats['vertices']} verts, "
            f"{stats['objects']} obj, {stats['materials']} mat, {stats['uv_layers']} uv"
        )
        lines.append(f"  size (m): {dims}")

    roundtrip = report.get("roundtrip")
    if roundtrip is not None:
        lines.append(
            f"  reimported: {roundtrip['triangles']} tris, {roundtrip['materials']} mat, "
            f"{roundtrip['uv_layers']} uv"
        )

    for entry in report.get("checks", []):
        mark = "ok  " if entry["ok"] else ("FAIL" if entry["severity"] == "error" else "warn")
        lines.append(f"  [{mark}] {entry['name']}: {entry['detail']}")

    for path_key, path_value in sorted(report.get("outputs", {}).items()):
        lines.append(f"  -> {path_key}: {path_value}")

    for message in report.get("errors", []):
        lines.append(f"  ERROR: {message}")

    trace = report.get("traceback")
    if trace:
        lines.append("--- traceback ---")
        lines.append(trace.rstrip())

    return "\n".join(lines)
