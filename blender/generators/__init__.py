"""Asset generators.

Every generator module exposes:
  MATERIAL_SLOTS: tuple[str, ...]   material slots the spec must provide
  build(spec: AssetSpec) -> assetkit.Asset          (kit generators, see docs/ASSETKIT.md)
                          or list[bpy.types.Object]  (generators not moved to the kit yet)

Register new modules in `blender/lib/registry.py`; kit generators also go in KIT_GENERATORS.
"""
