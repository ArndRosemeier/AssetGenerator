"""Host prerequisite checks for clone-and-go workflows.

Verifies everything a fresh machine needs *before* Blender download / asset
generation starts. Stdlib-only; safe to import from regenerate/bootstrap/doctor.
"""

from __future__ import annotations

import importlib
import os
import platform
import shutil
import sys
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from tools.blenderctl import (
    BLENDER_HOME,
    BLENDER_VERSION,
    RELEASE_URL,
    REPO_ROOT,
    find_blender,
)

Severity = Literal["error", "warning"]

MIN_PYTHON: Final[tuple[int, int]] = (3, 11)
REQUIRED_STDLIB: Final[tuple[str, ...]] = (
    "argparse",
    "hashlib",
    "json",
    "pathlib",
    "subprocess",
    "tempfile",
    "urllib.request",
    "zipfile",
)
# Rough headroom for the portable Blender zip + extract + a few baked assets.
MIN_FREE_BYTES_FOR_BOOTSTRAP: Final[int] = 2 * 1024 * 1024 * 1024  # 2 GiB
SPEC_DIR: Final[Path] = REPO_ROOT / "assets" / "specs"
OUT_DIR: Final[Path] = REPO_ROOT / "assets" / "out"
ENTRYPOINT_DIR: Final[Path] = REPO_ROOT / "blender" / "entrypoints"


@dataclass(frozen=True)
class PrereqCheck:
    name: str
    ok: bool
    severity: Severity
    detail: str
    fix: str = ""


def _check(name: str, ok: bool, detail: str, *, severity: Severity = "error", fix: str = "") -> PrereqCheck:
    return PrereqCheck(name=name, ok=ok, severity=severity, detail=detail, fix=fix)


def _free_bytes(path: Path) -> int | None:
    try:
        path.mkdir(parents=True, exist_ok=True)
        return shutil.disk_usage(path).free
    except OSError:
        return None


def _writable(path: Path) -> tuple[bool, str]:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True, f"{path} is writable"
    except OSError as exc:
        return False, f"{path} is not writable: {exc}"


def _probe_network() -> tuple[bool, str]:
    url = f"{RELEASE_URL}/"
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "asset-lab-prereqs/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - fixed https URL
            code = getattr(response, "status", None) or response.getcode()
            if code and int(code) >= 400:
                return False, f"{url} returned HTTP {code}"
            return True, f"reachable ({url})"
    except urllib.error.HTTPError as exc:
        # Some mirrors reject HEAD; a 403/405 on HEAD with GET working still means network is up.
        if exc.code in {403, 405, 501}:
            return True, f"reachable ({url}, HEAD->{exc.code})"
        return False, f"{url} returned HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 - report verbatim to the user
        return False, f"cannot reach {url}: {exc}"


def collect_prereqs(*, for_bootstrap: bool) -> list[PrereqCheck]:
    """Return host checks. `for_bootstrap=True` when Blender may still need downloading."""
    checks: list[PrereqCheck] = []

    version = sys.version_info
    py_ok = (version.major, version.minor) >= MIN_PYTHON
    checks.append(
        _check(
            "python_version",
            py_ok,
            f"Python {version.major}.{version.minor}.{version.micro} ({sys.executable})",
            fix=(
                f"Install Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ from https://www.python.org/downloads/ "
                "and ensure `python` is on PATH."
                if not py_ok
                else ""
            ),
        )
    )

    missing_mods: list[str] = []
    for module_name in REQUIRED_STDLIB:
        try:
            importlib.import_module(module_name)
        except ImportError:
            missing_mods.append(module_name)
    checks.append(
        _check(
            "python_stdlib",
            not missing_mods,
            "required modules importable" if not missing_mods else f"missing: {missing_mods}",
            fix="Use a normal CPython install (not a stripped embed). Reinstall Python if modules are missing.",
        )
    )

    checks.append(
        _check(
            "repo_layout",
            SPEC_DIR.is_dir() and ENTRYPOINT_DIR.is_dir(),
            f"specs={SPEC_DIR.is_dir()}, entrypoints={ENTRYPOINT_DIR.is_dir()}",
            fix="Clone the full repository; run commands from the repo root.",
        )
    )

    out_ok, out_detail = _writable(OUT_DIR)
    checks.append(
        _check(
            "output_writable",
            out_ok,
            out_detail,
            fix=f"Ensure you can write to {OUT_DIR} (permissions / disk full).",
        )
    )

    tools_ok, tools_detail = _writable(BLENDER_HOME)
    checks.append(
        _check(
            "blender_home_writable",
            tools_ok,
            tools_detail,
            fix=f"Ensure you can write to {BLENDER_HOME} so Blender can be downloaded/extracted.",
        )
    )

    blender = find_blender()
    if blender is not None:
        checks.append(
            _check(
                "blender",
                True,
                f"{blender.version_str} at {blender.executable} (via {blender.source})",
            )
        )
    else:
        can_auto = sys.platform == "win32"
        env_override = os.environ.get("BLENDER_BIN")
        if env_override:
            checks.append(
                _check(
                    "blender",
                    False,
                    f"BLENDER_BIN={env_override} does not point at a usable blender executable",
                    fix="Fix BLENDER_BIN or unset it and let bootstrap download the pinned build.",
                )
            )
        elif can_auto and for_bootstrap:
            checks.append(
                _check(
                    "blender",
                    True,
                    f"not installed yet; bootstrap will download Blender {BLENDER_VERSION}",
                    severity="warning",
                )
            )
            net_ok, net_detail = _probe_network()
            checks.append(
                _check(
                    "network_blender_cdn",
                    net_ok,
                    net_detail,
                    fix=(
                        "Allow HTTPS to download.blender.org (or install Blender yourself and set BLENDER_BIN)."
                    ),
                )
            )
            free = _free_bytes(BLENDER_HOME)
            if free is None:
                checks.append(
                    _check(
                        "disk_space",
                        False,
                        f"could not measure free space under {BLENDER_HOME}",
                        fix="Check that the drive is accessible.",
                    )
                )
            else:
                gib = free / (1024**3)
                checks.append(
                    _check(
                        "disk_space",
                        free >= MIN_FREE_BYTES_FOR_BOOTSTRAP,
                        f"{gib:.1f} GiB free on the Blender install drive",
                        fix=(
                            f"Free at least ~2 GiB for Blender {BLENDER_VERSION} download + extract."
                        ),
                    )
                )
        elif can_auto:
            checks.append(
                _check(
                    "blender",
                    False,
                    "Blender not found",
                    fix="Run `python tools/bootstrap.py` or `python tools/regenerate_assets.py`.",
                )
            )
        else:
            checks.append(
                _check(
                    "blender",
                    False,
                    f"Blender not found; auto-download is Windows-only (this is {sys.platform})",
                    fix=(
                        f"Install Blender {BLENDER_VERSION} (or {BLENDER_VERSION.rsplit('.', 1)[0]} LTS) "
                        "and set BLENDER_BIN to the blender executable."
                    ),
                )
            )

    # Soft note: machine identity for support / docs.
    checks.append(
        _check(
            "platform",
            True,
            f"{platform.system()} {platform.release()} ({platform.machine()})",
            severity="warning",
        )
    )

    return checks


def failed_errors(checks: Sequence[PrereqCheck]) -> list[PrereqCheck]:
    return [check for check in checks if not check.ok and check.severity == "error"]


def format_prereqs(checks: Sequence[PrereqCheck]) -> str:
    lines = ["=== prerequisite checks ==="]
    for check in checks:
        if check.ok:
            mark = "ok  "
        elif check.severity == "warning":
            mark = "warn"
        else:
            mark = "FAIL"
        lines.append(f"  [{mark}] {check.name}: {check.detail}")
        if not check.ok and check.fix:
            lines.append(f"         fix: {check.fix}")
    errors = failed_errors(checks)
    if errors:
        lines.append(f"Prerequisites FAILED ({len(errors)} error(s)).")
    else:
        lines.append("Prerequisites OK.")
    return "\n".join(lines)


class PrereqError(RuntimeError):
    """Raised when a hard prerequisite check fails."""


def require_prereqs(*, for_bootstrap: bool) -> list[PrereqCheck]:
    """Run checks, print the report, raise PrereqError on hard failures."""
    checks = collect_prereqs(for_bootstrap=for_bootstrap)
    print(format_prereqs(checks))
    errors = failed_errors(checks)
    if errors:
        names = ", ".join(check.name for check in errors)
        raise PrereqError(f"missing prerequisites: {names}")
    return checks
