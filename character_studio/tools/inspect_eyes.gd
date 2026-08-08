extends SceneTree
## Headless: verify each Character Studio human GLB has Eyes + 28 face morphs.


const ASSETS: Array[String] = [
	"res://assets/humans/male_base.glb",
	"res://assets/humans/female_base.glb",
	"res://assets/humans/outfits/male_casual_01.glb",
	"res://assets/humans/outfits/female_casual_01.glb",
]


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var failed := 0
	for path in ASSETS:
		if not ResourceLoader.exists(path):
			push_error("missing %s" % path)
			failed += 1
			continue
		var packed := load(path)
		if not (packed is PackedScene):
			push_error("%s is not a PackedScene" % path)
			failed += 1
			continue
		var root := (packed as PackedScene).instantiate()
		var face := _count_face(root)
		var eyes := _find_eyes(root)
		print(
			"inspect ",
			path.get_file(),
			" face_morphs=",
			face,
			" eyes=",
			eyes != null,
			" eyes_verts=",
			_mesh_verts(eyes)
		)
		if face < 28:
			push_error("%s: expected 28 face morphs, got %d" % [path, face])
			failed += 1
		if eyes == null:
			push_error("%s: no Eyes mesh" % path)
			failed += 1
		root.free()
	quit(1 if failed > 0 else 0)


func _count_face(n: Node) -> int:
	var best := 0
	if n is MeshInstance3D:
		var mesh := (n as MeshInstance3D).mesh as ArrayMesh
		if mesh != null:
			var c := 0
			for i in range(mesh.get_blend_shape_count()):
				if String(mesh.get_blend_shape_name(i)).begins_with("face_"):
					c += 1
			best = c
	for ch in n.get_children():
		best = maxi(best, _count_face(ch))
	return best


func _find_eyes(n: Node) -> MeshInstance3D:
	if n is MeshInstance3D and String(n.name).to_lower().contains("eye"):
		var mi := n as MeshInstance3D
		if mi.mesh != null:
			return mi
	for ch in n.get_children():
		var found := _find_eyes(ch)
		if found != null:
			return found
	return null


func _mesh_verts(mi: MeshInstance3D) -> int:
	if mi == null or mi.mesh == null:
		return 0
	var total := 0
	for s in range(mi.mesh.get_surface_count()):
		var arrays := mi.mesh.surface_get_arrays(s)
		var verts: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		total += verts.size()
	return total
