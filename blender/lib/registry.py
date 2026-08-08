"""Generator registry.

Maps the `generator` field of a spec to the module that builds it. Kept free of
`bpy` so the CLI can validate a generator name without launching Blender.
"""

from __future__ import annotations

from typing import Final

GENERATORS: Final[dict[str, str]] = {
    "hard_surface.crate": "blender.generators.hard_surface_crate",
    "nature.pine": "blender.generators.nature_pine",
    "nature.rock": "blender.generators.nature_rock",
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
