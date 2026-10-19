"""Generator registry.

Maps the `generator` field of a spec to the module that builds it. Kept free of
`bpy` so the CLI can validate a generator name without launching Blender.
"""

from __future__ import annotations

from typing import Final

GENERATORS: Final[dict[str, str]] = {
    "hard_surface.crate": "blender.generators.hard_surface_crate",
    "hard_surface.door": "blender.generators.hard_surface_door",
    "hard_surface.furniture": "blender.generators.hard_surface_furniture",
    "hard_surface.campfire": "blender.generators.hard_surface_campfire",
    "hard_surface.tent": "blender.generators.hard_surface_tent",
    "hard_surface.bridge_span": "blender.generators.hard_surface_bridge_span",
    "hard_surface.bridge_abutment": "blender.generators.hard_surface_bridge_abutment",
    "hard_surface.cabin": "blender.generators.hard_surface_cabin",
    "hard_surface.kit_cell": "blender.generators.hard_surface_kit_cell",
    "nature.pine": "blender.generators.nature_pine",
    "nature.broadleaf": "blender.generators.nature_broadleaf",
    "nature.willow": "blender.generators.nature_willow",
    "nature.cypress": "blender.generators.nature_cypress",
    "nature.snag": "blender.generators.nature_snag",
    "nature.palm": "blender.generators.nature_palm",
    "nature.birch": "blender.generators.nature_birch",
    "nature.grove": "blender.generators.nature_grove",
    "nature.fruit_tree": "blender.generators.nature_fruit_tree",
    "nature.rock": "blender.generators.nature_rock",
    "nature.grass_tuft": "blender.generators.nature_grass_tuft",
    "nature.sedge": "blender.generators.nature_sedge",
    "nature.mushroom": "blender.generators.nature_mushroom",
    "nature.berry_patch": "blender.generators.nature_berry_patch",
    "nature.reed": "blender.generators.nature_reed",
    "nature.bush": "blender.generators.nature_bush",
    "prop.kit": "blender.generators.prop_kit",
    "creature.crawler": "blender.generators.crawler_generator",
    "creature.quadruped": "blender.generators.quadruped_generator",
    "creature.mushroom": "blender.generators.mushroom_creature",
}


# Generators written against the asset kit (assetkit/): their `build` returns an `Asset` and they
# import no Blender module, so they run without Blender and do not change when Blender does.
# tests/test_assetkit.py holds every one of them to that; tools/backend_matrix.py builds their specs
# on each supported Blender version and requires the same result.
KIT_GENERATORS: Final[frozenset[str]] = frozenset({"hard_surface.crate", "prop.kit"})


class UnknownGeneratorError(KeyError):
    """Raised when a spec names a generator that does not exist."""


def resolve_generator_module(name: str) -> str:
    module = GENERATORS.get(name)
    if module is None:
        raise UnknownGeneratorError(
            f"Unknown generator '{name}'. Available: {sorted(GENERATORS)}"
        )
    return module
