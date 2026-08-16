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
    "hard_surface.bridge_span": "blender.generators.hard_surface_bridge_span",
    "hard_surface.bridge_abutment": "blender.generators.hard_surface_bridge_abutment",
    "hard_surface.cabin": "blender.generators.hard_surface_cabin",
    "hard_surface.kit_cell": "blender.generators.hard_surface_kit_cell",
    "nature.pine": "blender.generators.nature_pine",
    "nature.rock": "blender.generators.nature_rock",
    "nature.grass_tuft": "blender.generators.nature_grass_tuft",
    "nature.reed": "blender.generators.nature_reed",
    "nature.bush": "blender.generators.nature_bush",
    "creature.crawler": "blender.generators.crawler_generator",
}


class UnknownGeneratorError(KeyError):
    """Raised when a spec names a generator that does not exist."""


def resolve_generator_module(name: str) -> str:
    module = GENERATORS.get(name)
    if module is None:
        raise UnknownGeneratorError(
            f"Unknown generator '{name}'. Available: {sorted(GENERATORS)}"
        )
    return module
