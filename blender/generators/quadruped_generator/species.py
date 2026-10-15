"""The kinds of animal the quadruped generator makes, chosen by the spec's `species`.

Each is a body plan on the same skeleton naming (anatomy.py) and the same posing (pose.py, clips.py),
with its own shapes, coat and clips: everything else (sculpting, the bake, skinning, export) is shared.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from blender.generators.quadruped_generator import (
    anatomy,
    clips,
    coat,
    cricket_body,
    cricket_clips,
    rat_body,
    rat_clips,
    slime_body,
    slime_clips,
)
from blender.generators.quadruped_generator.anatomy import Body
from blender.generators.quadruped_generator.params import QuadrupedParams
from blender.generators.quadruped_generator.sculpt import ribs
from blender.generators.quadruped_generator.sdf import Grid
from blender.generators.quadruped_generator.skin import DEFAULT_SOFTNESS, SOFTNESS


@dataclass(frozen=True)
class Species:
    #: The body plan, from the spec's build number (`lean`: how much bone shows on a dog, how fat a rat is).
    body: Callable[[QuadrupedParams], Body]
    #: How far the coat stands off the skin: (points, normals, noise, fur length) -> offsets.
    fur: Callable[[np.ndarray, np.ndarray, coat.Noise, float], np.ndarray]
    #: The coat's colours: (points, normals, noise, palette, mange) -> linear RGB per point.
    colours: Callable[[np.ndarray, np.ndarray, coat.Noise, coat.Palette, float], np.ndarray]
    #: The bake's strand and tuft coordinates (texture.coat_material).
    hair: Callable[[np.ndarray], tuple[np.ndarray, np.ndarray]]
    clips: list[clips.Clip]
    softness: dict[str, float]
    default_softness: float
    #: Anything carved into the field after the shapes (the dog's ribs).
    detail: Callable[[Grid, QuadrupedParams], None] = lambda grid, params: None


SPECIES: dict[str, Species] = {
    "feral_dog": Species(
        body=lambda p: anatomy.feral_dog(p.lean),
        fur=coat.fur_offsets,
        colours=coat.coat_colours,
        hair=lambda p: (coat.hair_coords(p, 25.0, 200.0), coat.hair_coords(p, 8.0, 60.0)),
        clips=clips.CLIPS,
        softness=SOFTNESS,
        default_softness=DEFAULT_SOFTNESS,
        detail=lambda grid, p: ribs(grid, 0.003 * p.lean),
    ),
    "quarry_rat": Species(
        body=lambda p: rat_body.quarry_rat(p.lean),
        fur=rat_body.fur_offsets,
        colours=rat_body.coat_colours,
        hair=rat_body.hair,
        clips=rat_clips.CLIPS,
        softness=rat_body.SOFTNESS,
        default_softness=rat_body.DEFAULT_SOFTNESS,
    ),
    "cave_cricket": Species(
        body=lambda p: cricket_body.cave_cricket(p.lean),
        fur=cricket_body.fur_offsets,
        colours=cricket_body.coat_colours,
        hair=cricket_body.hair,
        clips=cricket_clips.CLIPS,
        softness=cricket_body.SOFTNESS,
        default_softness=cricket_body.DEFAULT_SOFTNESS,
    ),
    "lumen_slime": Species(
        body=lambda p: slime_body.slime(True, 0.0),
        fur=slime_body.fur_offsets,
        colours=slime_body.coat_colours,
        hair=slime_body.hair,
        clips=slime_clips.CLIPS,
        softness=slime_body.SOFTNESS,
        default_softness=slime_body.DEFAULT_SOFTNESS,
    ),
    "murk_slime": Species(
        body=lambda p: slime_body.slime(False, p.lean),
        fur=slime_body.fur_offsets,
        colours=slime_body.coat_colours,
        hair=slime_body.hair,
        clips=slime_clips.CLIPS,
        softness=slime_body.SOFTNESS,
        default_softness=slime_body.DEFAULT_SOFTNESS,
    ),
}
