# -*- coding: utf-8 -*-
"""Bake UAL Idle_Loop / Walk_Loop / Sword_Attack onto AG male_bandit_01 only.

Rest-relative retarget is identical to bake_human_idle_walk.py.
Does NOT touch civilian worksuit/casualsuit or City files.
"""
from __future__ import annotations

import json
import math
import shutil
import sys
import traceback
from pathlib import Path

import bpy

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import bake_human_idle_walk as B  # noqa: E402

BANDIT = Path(r"C:\Projekte\AssetGenerator\assets\humans\outfits\male_bandit_01.glb")
CITY_BANDIT = Path(r"C:\Projekte\City\assets\humans\outfits\male_bandit_01.glb")
CIVILIANS = (
    Path(r"C:\Projekte\AssetGenerator\assets\humans\male_dressed_male_worksuit01.glb"),
    Path(r"C:\Projekte\AssetGenerator\assets\humans\female_dressed_female_casualsuit01.glb"),
    Path(r"C:\Projekte\OrrunWithEngine\orrun\assets\humans\male_dressed_male_worksuit01.glb"),
    Path(r"C:\Projekte\OrrunWithEngine\orrun\assets\humans\female_dressed_female_casualsuit01.glb"),
)

CLIPS_WITH_ATTACK = [
    ("Idle_Loop", ("Idle", "Idle_Loop"), False),
    ("Walk_Loop", ("Walk", "Walk_Loop"), True),
    ("Sword_Attack", ("Attack", "Sword_Attack"), False),
]
CLIPS_IDLE_WALK = [
    ("Idle_Loop", ("Idle", "Idle_Loop"), False),
    ("Walk_Loop", ("Walk", "Walk_Loop"), True),
]

ATTACK_BONES = ("upperarm_r", "upperarm_l", "hand_r", "thigh_l")


def log(msg: str) -> None:
    print(f"[bandit-bake] {msg}", flush=True)


def snapshot(paths):
    out = {}
    for p in paths:
        if p.is_file():
            st = p.stat()
            out[str(p)] = (st.st_size, int(st.st_mtime))
        else:
            out[str(p)] = None
    return out


def assert_untouched(before, label):
    after = snapshot([Path(k) for k in before])
    dirty = []
    for k, v in before.items():
        if after.get(k) != v:
            dirty.append((k, v, after.get(k)))
    if dirty:
        raise RuntimeError(f"{label} files changed: {dirty}")
    log(f"{label} untouched ({len(before)} paths)")


def mid_rot(doc, blob, anims, names, clip, bone):
    anim = anims.get(clip)
    if not anim:
        return None, 0.0
    for ch in anim.get("channels", []):
        tgt = ch.get("target", {})
        if names.get(tgt.get("node")) != bone or tgt.get("path") != "rotation":
            continue
        samp = anim["samplers"][ch["sampler"]]
        times, _ = B.read_accessor(doc, blob, samp["input"])
        rots, _ = B.read_accessor(doc, blob, samp["output"])
        if not rots:
            return None, 0.0
        t0, t1 = times[0], times[-1]
        mid_t = t0 + 0.5 * (t1 - t0)
        best_i = min(range(len(times)), key=lambda i: abs(times[i] - mid_t))
        span = 0.0
        for r in rots:
            span = max(span, math.degrees(B.quat_angle(r, rots[0])))
        return rots[best_i], span
    return None, 0.0


def verify_bandit(path: Path) -> dict:
    res = B.verify_glb(path)
    doc, blob = B.glb_chunks(path)
    names = B.node_name_map(doc)
    anims = {a.get("name"): a for a in doc.get("animations", [])}
    rest_rots = {n.get("name"): tuple(n.get("rotation") or (0, 0, 0, 1)) for n in doc.get("nodes", [])}

    res["source"] = None
    res["attack_ok"] = False
    res["attack_notes"] = []
    res["attack_metrics"] = {}

    attack_name = "Attack" if "Attack" in anims else ("Sword_Attack" if "Sword_Attack" in anims else None)
    if not attack_name:
        res["attack_notes"].append("no Attack/Sword_Attack clip")
        return res

    bones = {}
    for ch in anims[attack_name].get("channels", []):
        tgt = ch.get("target", {})
        bones.setdefault(names.get(tgt.get("node"), "?"), set()).add(tgt.get("path"))
    res["attack_metrics"]["channels"] = len(bones)
    if len(bones) < 6:
        res["attack_notes"].append(f"{attack_name} only {len(bones)} bones (empty/frozen)")
        return res
    missing = [b for b in B.VERIFY_BONES if b not in bones]
    if missing:
        res["attack_notes"].append(f"{attack_name} missing {missing}")
        return res

    spans = []
    vs_rest = []
    vs_idle = []
    for bone in ATTACK_BONES:
        att, span = mid_rot(doc, blob, anims, names, attack_name, bone)
        idle, _ = mid_rot(doc, blob, anims, names, "Idle", bone)
        rest = rest_rots.get(bone, (0, 0, 0, 1))
        if att is None:
            res["attack_notes"].append(f"{attack_name} no rotation on {bone}")
            continue
        spans.append(span)
        vs_rest.append(math.degrees(B.quat_angle(att, rest)))
        if idle is not None:
            d = math.degrees(B.quat_angle(att, idle))
            vs_idle.append(d)
        res["attack_metrics"][bone] = {
            "span": round(span, 3),
            "vs_idle": round(vs_idle[-1], 3) if vs_idle else None,
            "vs_rest": round(vs_rest[-1], 3) if vs_rest else None,
        }

    max_vs_idle = max(vs_idle) if vs_idle else 0.0
    max_span = max(spans) if spans else 0.0
    max_vs_rest = max(vs_rest) if vs_rest else 0.0
    res["attack_metrics"]["max_vs_idle"] = round(max_vs_idle, 3)
    res["attack_metrics"]["max_span"] = round(max_span, 3)
    res["attack_metrics"]["max_vs_rest"] = round(max_vs_rest, 3)

    if max_vs_idle < 8.0:
        res["attack_notes"].append(f"{attack_name} same as Idle (max {max_vs_idle:.2f} deg)")
        return res
    if max_span < 8.0:
        res["attack_notes"].append(f"{attack_name} frozen (max span {max_span:.2f} deg)")
        return res
    if max_vs_rest < 4.0:
        res["attack_notes"].append(f"{attack_name} T-pose-ish vs rest (max {max_vs_rest:.2f} deg)")
        return res

    res["attack_ok"] = True
    return res


def bake_with(clips) -> dict:
    B.CLIPS = clips
    B.REQUIRED_CLIPS = ("Idle", "Walk")
    B.TARGETS = [BANDIT]
    B.bake_one(BANDIT)
    res = verify_bandit(BANDIT)
    log(res["line"])
    log(f"attack_ok={res['attack_ok']} metrics={res.get('attack_metrics')} notes={res.get('attack_notes')}")
    return res


def main() -> int:
    B.ensure_scratch()
    log(f"blender {bpy.app.version_string}")
    if not B.SRC_ANIM.is_file():
        raise FileNotFoundError(B.SRC_ANIM)
    if not BANDIT.is_file():
        raise FileNotFoundError(BANDIT)
    if BANDIT.resolve() == CITY_BANDIT.resolve():
        raise RuntimeError("refusing to write City bandit")

    guard = snapshot(list(CIVILIANS) + [CITY_BANDIT])
    bak = BANDIT.with_suffix(".glb.bak")
    if not bak.is_file():
        shutil.copy2(BANDIT, bak)
        log(f"backup created {bak} ({bak.stat().st_size} bytes)")
    else:
        log(f"backup exists {bak} ({bak.stat().st_size} bytes)")

    source = None
    try:
        res = bake_with(CLIPS_WITH_ATTACK)
        if res["ok"] and res["attack_ok"]:
            source = "UAL"
            log("UAL Sword_Attack landed")
        else:
            reason = "; ".join(res.get("attack_notes") or res.get("notes") or ["unknown"])
            log(f"UAL Attack failed ({reason}); Mixamo sword FBX not on disk; shipping Idle+Walk")
            B.restore_from_bak(BANDIT)
            res = bake_with(CLIPS_IDLE_WALK)
            source = "idle/walk only"
            res["attack_ok"] = False
            res["attack_notes"].append("UAL Attack failed; Mixamo sword not on disk")
            if not res["ok"]:
                B.restore_from_bak(BANDIT)
                raise RuntimeError("Idle+Walk bake failed: " + "; ".join(res.get("notes") or []))
        res["source"] = source
        res["dest"] = str(BANDIT)
        res["backup"] = str(bak)
        report = B.SCRATCH / "bandit_verify.json"
        report.write_text(json.dumps(res, indent=2), encoding="utf-8")
        (B.SCRATCH / "bandit_verify.txt").write_text(
            f"source={source}\ndest={BANDIT}\n{res['line']}\nattack={res.get('attack_metrics')}\nnotes={res.get('notes')}\nattack_notes={res.get('attack_notes')}\n",
            encoding="utf-8",
        )
        assert_untouched(guard, "civilian/City")
        log(f"DONE source={source} dest={BANDIT} size={BANDIT.stat().st_size}")
        return 0
    except Exception:
        traceback.print_exc()
        if bak.is_file():
            B.restore_from_bak(BANDIT)
        assert_untouched(guard, "civilian/City")
        return 1


if __name__ == "__main__":
    try:
        code = main()
    except Exception:
        traceback.print_exc()
        code = 1
    sys.exit(code)
