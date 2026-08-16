extends SceneTree
## Headless: verify the exported modular set before launching the studio.
##
## Bodies must carry eyes and the 28 face morphs; every per-suit body must be
## lighter than the nude one and include its clothing mesh; every wardrobe
## piece must ship a skinned mesh.


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var catalog := WardrobeCatalog.load_default()
	if catalog.is_empty():
		push_error("wardrobe.json lists no garments")
		quit(1)
		return

	var failed := 0
	for female in [false, true]:
		var sex := "female" if female else "male"
		var nude_verts := _check_body(catalog.body_path(female, ""), sex + " nude")
		if nude_verts <= 0:
			failed += 1
			continue
		for suit in catalog.items_for(female, "suit"):
			var suit_id := String(suit["id"])
			var path := catalog.body_path(female, suit_id)
			var verts := _check_body(path, suit_id + " body")
			if verts <= 0:
				failed += 1
			elif verts >= nude_verts:
				push_error(
					"%s body is not masked (%d verts vs nude %d)" % [suit_id, verts, nude_verts]
				)
				failed += 1
			elif _count_clothes(path) < 1:
				push_error("%s dressed body has no clothing mesh" % suit_id)
				failed += 1

	for slot in catalog.slots:
		for female in [false, true]:
			for item in catalog.items_for(female, slot):
				if not _check_piece(String(item["path"])):
					failed += 1

	quit(1 if failed > 0 else 0)


## Returns the body's vertex count, or 0 when a check failed.
func _check_body(path: String, label: String) -> int:
	var root := _instantiate(path)
	if root == null:
		return 0
	var face := _count_face(root)
	var eyes := _find_eyes(root)
	var verts := _count_body_verts(root)
	print("inspect ", label, " face_morphs=", face, " eyes=", eyes != null, " body_verts=", verts)
	var ok := true
	if face < 28:
		push_error("%s: expected 28 face morphs, got %d" % [path, face])
		ok = false
	if eyes == null:
		push_error("%s: no Eyes mesh" % path)
		ok = false
	root.free()
	return verts if ok else 0


func _check_piece(path: String) -> bool:
	var root := _instantiate(path)
	if root == null:
		return false
	var skinned := _count_skinned(root)
	print("inspect ", path.get_file(), " skinned_meshes=", skinned, " verts=", _count_verts(root))
	root.free()
	if skinned < 1:
		push_error("%s: no skinned mesh" % path)
		return false
	return true


func _instantiate(path: String) -> Node:
	if not ResourceLoader.exists(path):
		push_error("missing %s" % path)
		return null
	var packed := load(path)
	if not (packed is PackedScene):
		push_error("%s is not a PackedScene" % path)
		return null
	return (packed as PackedScene).instantiate()


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


func _count_skinned(n: Node) -> int:
	var total := 0
	if n is MeshInstance3D:
		var mi := n as MeshInstance3D
		if mi.mesh != null and mi.skin != null:
			total += 1
	for ch in n.get_children():
		total += _count_skinned(ch)
	return total


func _count_verts(n: Node) -> int:
	var total := 0
	if n is MeshInstance3D:
		var mi := n as MeshInstance3D
		if mi.mesh != null:
			total += _surface_verts(mi.mesh)
	for ch in n.get_children():
		total += _count_verts(ch)
	return total


func _count_body_verts(n: Node) -> int:
	if n is MeshInstance3D:
		var mesh := (n as MeshInstance3D).mesh as ArrayMesh
		if mesh != null and _face_morphs(mesh) >= 28:
			return _surface_verts(mesh)
	for ch in n.get_children():
		var found := _count_body_verts(ch)
		if found > 0:
			return found
	return 0


func _count_clothes(path: String) -> int:
	var root := _instantiate(path)
	if root == null:
		return 0
	var count := _count_clothes_meshes(root)
	root.free()
	return count


func _count_clothes_meshes(n: Node) -> int:
	var total := 0
	if n is MeshInstance3D:
		var mi := n as MeshInstance3D
		if mi.mesh != null and mi.skin != null:
			var name := String(mi.name).to_lower()
			var mesh := mi.mesh as ArrayMesh
			var is_eyes := name.contains("eye")
			var is_body := mesh != null and _face_morphs(mesh) >= 28
			if not is_eyes and not is_body:
				total += 1
	for ch in n.get_children():
		total += _count_clothes_meshes(ch)
	return total


func _face_morphs(mesh: ArrayMesh) -> int:
	var c := 0
	for i in range(mesh.get_blend_shape_count()):
		if String(mesh.get_blend_shape_name(i)).begins_with("face_"):
			c += 1
	return c


func _surface_verts(mesh: Mesh) -> int:
	var total := 0
	for s in range(mesh.get_surface_count()):
		var arrays := mesh.surface_get_arrays(s)
		var verts: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		total += verts.size()
	return total


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
