"""Asset generators.

Every generator module exposes:
  MATERIAL_SLOTS: tuple[str, ...]   material slots the spec must provide
  build(spec: AssetSpec) -> list[bpy.types.Object]

Register new modules in `blender/lib/registry.py`.
"""
