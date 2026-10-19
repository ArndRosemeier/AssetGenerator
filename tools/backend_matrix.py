"""Build the same specs on several Blender versions: the contract must hold, changes are shown.

A kit generator (assetkit/) says what an asset is; the Blender backend decides how
to make it, and may make it better on a newer Blender. So versions are not required
to agree. They are held to the spec's contract, and every other difference is
reported so an upgrade never changes an asset silently.

Each install builds each spec through the normal `generate` entrypoint, then the
shipped .glb files are read back and compared with the first install's.

    python tools/backend_matrix.py --python bpy45/bin/python --python bpy52/bin/python
    python tools/backend_matrix.py --blender /opt/b45/blender --blender /opt/b52/blender prop_barrel

Without spec ids it builds every spec of every kit generator (KIT_GENERATORS).

BROKEN   the contract fails on a version: a QA gate or the export round trip, the
         material slots, or the asset's size (more than 1 mm off). Exit 1.
changed  the contract holds but the geometry or the UV layout differs: a better
         bevel, a different unwrap. Listed, not failed (`--strict` fails it).
same     same geometry to 0.1 mm and the same UV layout.

Exit codes: 0 contract holds everywhere, 1 something BROKEN (or changed, with
--strict), 2 bad arguments or toolchain.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Final

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from blender.lib.glb import Glb
from blender.lib.registry import KIT_GENERATORS
from blender.lib.spec import AssetSpec, SpecError, load_spec
from tools.ag import OUT_DIR, SPEC_DIR, list_spec_paths, load_and_check_spec
from tools.blenderctl import BlenderError, BlenderInstall, binary_install, module_install, run_entrypoint

SIZE_TOLERANCE: Final[float] = 1e-3  # metres: the contract on an asset's bounds
POSITION_TOLERANCE: Final[float] = 1e-4  # metres: "same geometry"
RELATIVE_TOLERANCE: Final[float] = 1e-5  # area, volume


def fingerprint(path: Path) -> dict[str, object]:
    """What a .glb holds, in numbers that do not depend on vertex order."""
    glb = Glb(path)
    positions: list[tuple[float, ...]] = []
    area = volume = 0.0
    triangles = 0
    uv_digest = hashlib.sha256()
    for mesh in glb.doc.get("meshes", []):
        for primitive in mesh["primitives"]:
            points = glb.values(primitive["attributes"]["POSITION"])
            positions.extend(points)
            if "TEXCOORD_0" in primitive["attributes"]:
                for uv in glb.values(primitive["attributes"]["TEXCOORD_0"]):
                    uv_digest.update(f"{uv[0]:.4f},{uv[1]:.4f};".encode())
            corners = [i[0] for i in glb.values(primitive["indices"])]
            for k in range(0, len(corners), 3):
                a, b, c = (points[corners[k + j]] for j in range(3))
                ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
                ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
                cross = (
                    ab[1] * ac[2] - ab[2] * ac[1],
                    ab[2] * ac[0] - ab[0] * ac[2],
                    ab[0] * ac[1] - ab[1] * ac[0],
                )
                area += 0.5 * math.sqrt(sum(x * x for x in cross))
                volume += (
                    a[0] * (b[1] * c[2] - b[2] * c[1])
                    - a[1] * (b[0] * c[2] - b[2] * c[0])
                    + a[2] * (b[0] * c[1] - b[1] * c[0])
                ) / 6.0
            triangles += len(corners) // 3
    lower = [min(p[i] for p in positions) for i in range(3)]
    upper = [max(p[i] for p in positions) for i in range(3)]
    return {
        "vertices": len(positions),
        "triangles": triangles,
        "materials": len(glb.doc.get("materials", [])),
        "bounds": [lower, upper],
        "area": area,
        "volume": volume,
        "positions": sorted(tuple(round(x, 4) for x in p) for p in positions),
        "uv_digest": uv_digest.hexdigest()[:12],
    }


def _bounds_gap(a: dict[str, object], b: dict[str, object]) -> float:
    pairs = (zip(a["bounds"][side], b["bounds"][side], strict=True) for side in (0, 1))  # type: ignore[index]
    return max(abs(x - y) for pair in pairs for x, y in pair)


def _contract_breaks(a: dict[str, object], b: dict[str, object]) -> list[str]:
    """What a spec promises whatever Blender builds it: its materials and its size."""
    found = []
    if a["materials"] != b["materials"]:
        found.append(f"materials {a['materials']} vs {b['materials']}")
    gap = _bounds_gap(a, b)
    if gap > SIZE_TOLERANCE:
        found.append(f"size differs by {gap:.4f} m")
    return found


def _changes(a: dict[str, object], b: dict[str, object]) -> list[str]:
    """Differences the contract allows: shown, so an upgrade never changes an asset unseen."""
    found = []
    for key in ("vertices", "triangles"):
        if a[key] != b[key]:
            found.append(f"{key} {a[key]} vs {b[key]}")
    gap = _bounds_gap(a, b)
    if POSITION_TOLERANCE < gap <= SIZE_TOLERANCE:
        found.append(f"size differs by {gap:.5f} m")
    for key in ("area", "volume"):
        x, y = float(a[key]), float(b[key])  # type: ignore[arg-type]
        if abs(x - y) > RELATIVE_TOLERANCE * max(abs(x), abs(y), 1e-9):
            found.append(f"{key} {x:.6f} vs {y:.6f}")
    if not found:
        moved = max(
            (
                abs(p - q)
                for u, v in zip(a["positions"], b["positions"], strict=True)  # type: ignore[call-overload]
                for p, q in zip(u, v, strict=True)
            ),
            default=0.0,
        )
        if moved > POSITION_TOLERANCE * 2:
            found.append(f"vertices moved by up to {moved:.6f} m")
    if a["uv_digest"] != b["uv_digest"]:
        found.append("UV layout differs")
    return found


def _installs(args: argparse.Namespace) -> list[BlenderInstall]:
    installs = [module_install(Path(p), "--python") for p in args.python or []]
    installs += [binary_install(Path(p), "--blender") for p in args.blender or []]
    if len(installs) < 2:
        raise BlenderError("Name at least two Blender installs (--python and/or --blender)")
    return installs


def _specs(references: list[str]) -> list[AssetSpec]:
    if references:
        return [load_and_check_spec(reference) for reference in references]
    specs = [load_spec(path) for path in list_spec_paths()]
    chosen = [spec for spec in specs if spec.generator in KIT_GENERATORS]
    if not chosen:
        raise SpecError(f"No spec in {SPEC_DIR} uses a kit generator {sorted(KIT_GENERATORS)}")
    return chosen


def _build_all(
    install: BlenderInstall, specs: list[AssetSpec], out_dir: Path
) -> dict[str, dict[str, object]]:
    results: dict[str, dict[str, object]] = {}
    for spec in specs:
        payload = {"spec_path": str(spec.source_path), "out_dir": str(out_dir)}
        report = run_entrypoint(install, "generate", payload).report
        entry: dict[str, object] = {"ok": bool(report.get("ok")), "errors": report.get("errors", [])}
        failed = [c["name"] for c in report.get("checks", []) if not c["ok"]]  # type: ignore[union-attr, index]
        entry["failed_checks"] = failed
        glb = out_dir / spec.glb_name
        if glb.is_file():
            entry["fingerprint"] = fingerprint(glb)
        results[spec.asset_id] = entry
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="backend_matrix", description=__doc__.split("\n\n")[0])
    parser.add_argument("specs", nargs="*", help="spec ids or paths (default: every kit generator spec)")
    parser.add_argument("--python", action="append", help="a Python that has the bpy module (repeatable)")
    parser.add_argument("--blender", action="append", help="a Blender binary (repeatable)")
    parser.add_argument("--json", action="store_true", help="print the raw comparison")
    parser.add_argument("--strict", action="store_true", help="fail on changes too, not only on breaks")
    args = parser.parse_args(argv)
    try:
        installs = _installs(args)
        specs = _specs(args.specs)
    except (SpecError, BlenderError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    labels = [f"blender-{install.version_str}" for install in installs]
    if len(set(labels)) != len(labels):
        print(f"error: two installs are the same version: {labels}", file=sys.stderr)
        return 2
    with ThreadPoolExecutor(max_workers=len(installs)) as pool:
        runs = list(
            pool.map(
                lambda pair: _build_all(pair[0], specs, OUT_DIR / "matrix" / pair[1]),
                zip(installs, labels, strict=True),
            )
        )

    counts = {"same": 0, "changed": 0, "BROKEN": 0}
    table: dict[str, dict[str, object]] = {}
    for spec in specs:
        entries = [run[spec.asset_id] for run in runs]
        broken: list[str] = []
        changed: list[str] = []
        for label, entry in zip(labels, entries, strict=True):
            if not entry["ok"]:
                broken.append(f"{label} failed: {entry['failed_checks'] or entry['errors']}")
        prints = [entry.get("fingerprint") for entry in entries]
        if all(prints):
            for label, other in zip(labels[1:], prints[1:], strict=True):
                broken += [f"{labels[0]} vs {label}: {d}" for d in _contract_breaks(prints[0], other)]  # type: ignore[arg-type]
                changed += [f"{labels[0]} vs {label}: {d}" for d in _changes(prints[0], other)]  # type: ignore[arg-type]
        status = "BROKEN" if broken else "changed" if changed else "same"
        counts[status] += 1
        table[spec.asset_id] = {"status": status, "broken": broken, "changed": changed}
        if not args.json:
            tris = "/".join(str(p["triangles"]) if p else "?" for p in prints)  # type: ignore[index]
            print(f"{status:8} {spec.asset_id:32} {tris} tris")
            for note in broken + changed:
                print(f"         {note}")

    if args.json:
        print(json.dumps({"installs": labels, "counts": counts, "assets": table}, indent=2))
    else:
        print(
            f"\n{', '.join(labels)}: {counts['same']} same, {counts['changed']} changed, "
            f"{counts['BROKEN']} broken (of {len(specs)})"
        )
    failing = counts["BROKEN"] + (counts["changed"] if args.strict else 0)
    return 1 if failing else 0


if __name__ == "__main__":
    raise SystemExit(main())
