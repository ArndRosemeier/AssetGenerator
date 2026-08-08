"""Locate, install and drive a headless Blender.

This module is the only place that knows how Blender is found and invoked.
It is stdlib-only so it runs on a bare Python install with no `pip install`.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
TOOLS_DIR: Final[Path] = REPO_ROOT / "tools"
BLENDER_HOME: Final[Path] = TOOLS_DIR / "blender-bin"
BLENDER_PATH_FILE: Final[Path] = TOOLS_DIR / ".blender_path"
ENTRYPOINT_DIR: Final[Path] = REPO_ROOT / "blender" / "entrypoints"

BLENDER_VERSION: Final[str] = "4.5.12"
BLENDER_SERIES: Final[str] = "4.5"
RELEASE_URL: Final[str] = f"https://download.blender.org/release/Blender{BLENDER_SERIES}"

# sha256 of the official portable archives for the pinned version, taken from
# https://download.blender.org/release/Blender4.5/blender-4.5.12.sha256
ARCHIVE_SHA256: Final[dict[str, str]] = {
    "blender-4.5.12-windows-x64.zip": "317ef64e7a2c3cc79ec810c766ae9828aff865bea78039dc695b3f1118c34b4f",
    "blender-4.5.12-windows-arm64.zip": "0bae137dc02418e846c5fe75997277be86fa923a1d64c75415b229cfdf22b18b",
}

_VERSION_RE: Final[re.Pattern[str]] = re.compile(r"Blender\s+(\d+)\.(\d+)\.(\d+)")


class BlenderError(RuntimeError):
    """Raised when Blender cannot be found, installed or executed."""


@dataclass(frozen=True)
class BlenderInstall:
    executable: Path
    version: tuple[int, int, int]
    source: str

    @property
    def version_str(self) -> str:
        return ".".join(str(part) for part in self.version)

    @property
    def series(self) -> str:
        return f"{self.version[0]}.{self.version[1]}"


@dataclass(frozen=True)
class RunResult:
    exit_code: int
    stdout: str
    stderr: str
    report: dict[str, object]


def _archive_name() -> str:
    if sys.platform != "win32":
        raise BlenderError(
            f"Automatic Blender install is implemented for Windows only (this is {sys.platform}). "
            f"Install Blender {BLENDER_SERIES} LTS yourself and point BLENDER_BIN at the executable."
        )
    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64"}:
        arch = "x64"
    elif machine in {"arm64", "aarch64"}:
        arch = "arm64"
    else:
        raise BlenderError(f"Unsupported Windows architecture: {platform.machine()!r}")
    return f"blender-{BLENDER_VERSION}-windows-{arch}.zip"


def _managed_root() -> Path:
    return BLENDER_HOME / _archive_name().removesuffix(".zip")


def _executable_name() -> str:
    return "blender.exe" if sys.platform == "win32" else "blender"


def _candidate_paths() -> list[tuple[Path, str]]:
    """Every place we look for a Blender executable, in priority order."""
    candidates: list[tuple[Path, str]] = []

    env_value = os.environ.get("BLENDER_BIN")
    if env_value:
        candidates.append((Path(env_value), "BLENDER_BIN"))

    if BLENDER_PATH_FILE.is_file():
        recorded = BLENDER_PATH_FILE.read_text(encoding="utf-8").strip()
        if recorded:
            candidates.append((Path(recorded), str(BLENDER_PATH_FILE)))

    if sys.platform == "win32":
        candidates.append((_managed_root() / "blender.exe", "managed install"))
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        foundation = program_files / "Blender Foundation"
        if foundation.is_dir():
            for entry in sorted(foundation.iterdir(), reverse=True):
                candidates.append((entry / "blender.exe", "Program Files"))
    else:
        candidates.append((_managed_root() / "blender", "managed install"))
        candidates.append((Path("/usr/bin/blender"), "system"))
        candidates.append((Path("/Applications/Blender.app/Contents/MacOS/Blender"), "system"))

    on_path = shutil.which(_executable_name())
    if on_path:
        candidates.append((Path(on_path), "PATH"))

    return candidates


def probe_version(executable: Path) -> tuple[int, int, int]:
    """Return the (major, minor, patch) version reported by a Blender binary."""
    completed = subprocess.run(
        [str(executable), "--version"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    match = _VERSION_RE.search(completed.stdout)
    if match is None:
        raise BlenderError(
            f"Could not parse a version from `{executable} --version`.\n"
            f"stdout: {completed.stdout.strip()[:500]}\n"
            f"stderr: {completed.stderr.strip()[:500]}"
        )
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def find_blender() -> BlenderInstall | None:
    """Return the first usable Blender install, or None if there is none."""
    seen: set[Path] = set()
    for path, source in _candidate_paths():
        resolved = path.resolve()
        if resolved in seen or not resolved.is_file():
            continue
        seen.add(resolved)
        return BlenderInstall(executable=resolved, version=probe_version(resolved), source=source)
    return None


def require_blender() -> BlenderInstall:
    install = find_blender()
    if install is None:
        raise BlenderError(
            "No Blender found. Run `python tools/bootstrap.py` to install the pinned "
            f"Blender {BLENDER_VERSION}, or set BLENDER_BIN to an existing install."
        )
    return install


def _download(url: str, destination: Path) -> None:
    print(f"Downloading {url}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # download.blender.org answers 403 to urllib's default User-Agent.
    request = urllib.request.Request(url, headers={"User-Agent": "asset-lab-bootstrap/1.0"})
    with urllib.request.urlopen(request) as response:  # noqa: S310 - fixed https URL
        total = int(response.headers.get("Content-Length", "0"))
        downloaded = 0
        last_reported = -1
        with destination.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 512)
                if not chunk:
                    break
                handle.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    percent = downloaded * 100 // total
                    if percent >= last_reported + 10:
                        last_reported = percent - percent % 10
                        print(f"  {last_reported:3d}%  {downloaded / 1e6:7.1f} / {total / 1e6:.1f} MB")
        print(f"  done  {downloaded / 1e6:.1f} MB")


def _verify_sha256(archive: Path, expected: str) -> None:
    digest = hashlib.sha256()
    with archive.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual != expected:
        archive.unlink()
        raise BlenderError(
            f"Checksum mismatch for {archive.name}.\n  expected {expected}\n  actual   {actual}\n"
            "The download was deleted. Re-run bootstrap."
        )


def install_pinned_blender() -> BlenderInstall:
    """Download, verify and extract the pinned Blender into the repo."""
    archive_name = _archive_name()
    expected_sha = ARCHIVE_SHA256.get(archive_name)
    if expected_sha is None:
        raise BlenderError(f"No pinned checksum recorded for {archive_name}")

    target_root = _managed_root()
    executable = target_root / _executable_name()
    if executable.is_file():
        return BlenderInstall(
            executable=executable.resolve(),
            version=probe_version(executable),
            source="managed install",
        )

    BLENDER_HOME.mkdir(parents=True, exist_ok=True)
    archive_path = BLENDER_HOME / archive_name
    if not archive_path.is_file():
        _download(f"{RELEASE_URL}/{archive_name}", archive_path)
    print("Verifying checksum")
    _verify_sha256(archive_path, expected_sha)

    print(f"Extracting to {target_root}")
    extract_tmp = Path(tempfile.mkdtemp(dir=BLENDER_HOME, prefix="_extract-"))
    with zipfile.ZipFile(archive_path) as zf:
        zf.extractall(extract_tmp)
    inner = [entry for entry in extract_tmp.iterdir() if entry.is_dir()]
    if len(inner) != 1:
        raise BlenderError(f"Unexpected archive layout: {[e.name for e in extract_tmp.iterdir()]}")
    if target_root.exists():
        shutil.rmtree(target_root)
    shutil.move(str(inner[0]), str(target_root))
    shutil.rmtree(extract_tmp, ignore_errors=True)
    archive_path.unlink()

    if not executable.is_file():
        raise BlenderError(f"Extraction finished but {executable} is missing")
    return BlenderInstall(
        executable=executable.resolve(),
        version=probe_version(executable),
        source="managed install",
    )


def record_blender_path(install: BlenderInstall) -> None:
    BLENDER_PATH_FILE.write_text(str(install.executable), encoding="utf-8")


def run_entrypoint(
    install: BlenderInstall,
    entrypoint: str,
    payload: dict[str, object],
) -> RunResult:
    """Run a Blender entrypoint script headlessly and return its JSON report.

    The script contract: it reads `--payload <file>`, writes `--result <file>`,
    and exits non-zero on failure. Blender's stdout is noisy, so the report file
    is the only channel we trust for structured data.
    """
    script = ENTRYPOINT_DIR / f"{entrypoint}.py"
    if not script.is_file():
        raise BlenderError(f"Unknown entrypoint: {script}")

    workdir = Path(tempfile.mkdtemp(prefix="assetlab-"))
    payload_file = workdir / "payload.json"
    result_file = workdir / "result.json"
    payload_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    command = [
        str(install.executable),
        "--background",
        "--factory-startup",
        "-noaudio",
        "--addons",
        "io_scene_gltf2",
        "--python-exit-code",
        "1",
        "--python",
        str(script),
        "--",
        "--payload",
        str(payload_file),
        "--result",
        str(result_file),
    ]

    completed = subprocess.run(command, capture_output=True, text=True)

    if not result_file.is_file():
        shutil.rmtree(workdir, ignore_errors=True)
        raise BlenderError(
            f"Blender exited with code {completed.returncode} and wrote no report.\n"
            f"--- stdout ---\n{completed.stdout}\n--- stderr ---\n{completed.stderr}"
        )
    report_text = result_file.read_text(encoding="utf-8")
    shutil.rmtree(workdir, ignore_errors=True)

    parsed = json.loads(report_text)
    if not isinstance(parsed, dict):
        raise BlenderError(f"Report is not a JSON object: {report_text[:500]}")

    return RunResult(
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        report=parsed,
    )
