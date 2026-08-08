extends SceneTree
## Headless smoke: the modular character assembles with eyes, morphs and garments.


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var packed := load("res://scenes/main.tscn")
	if not (packed is PackedScene):
		push_error("main.tscn missing")
		quit(2)
		return
	var root := (packed as PackedScene).instantiate()
	get_root().add_child(root)
	await process_frame
	await process_frame
	var body := root.get_node_or_null("Body")
	if body == null:
		push_error("Body not spawned")
		quit(1)
		return
	var face := _count_face(body)
	var eyes := _find_eyes(body)
	var skeleton := _find_skeleton(body)
	var pieces := _collect_pieces(body)
	print(
		"smoke body_ok face_morphs=", face,
		" eyes=", eyes != null,
		" pieces=", pieces.size()
	)
	if face < 28:
		push_error("expected 28 face morphs, got %d" % face)
		quit(1)
		return
	if eyes == null:
		push_error("no Eyes mesh in the spawned body")
		quit(1)
		return
	if eyes.mesh.get_surface_count() < 1:
		push_error("Eyes mesh has no surface")
		quit(1)
		return
	if skeleton == null:
		push_error("no Skeleton3D in the spawned body")
		quit(1)
		return
	if pieces.size() < 4:
		push_error(
			"expected default suit/shoes/hair/eyebrows to be attached, got %d" % pieces.size()
		)
		quit(1)
		return
	for piece in pieces:
		if piece.get_node_or_null(piece.skeleton) != skeleton:
			push_error("garment %s is not bound to the body skeleton" % piece.name)
			quit(1)
			return
	quit(0)


func _collect_pieces(n: Node) -> Array[MeshInstance3D]:
	var found: Array[MeshInstance3D] = []
	if n is MeshInstance3D and n.is_in_group(&"ModularPiece"):
		found.append(n as MeshInstance3D)
	for ch in n.get_children():
		found.append_array(_collect_pieces(ch))
	return found


func _find_skeleton(n: Node) -> Skeleton3D:
	if n is Skeleton3D:
		return n as Skeleton3D
	for ch in n.get_children():
		var found := _find_skeleton(ch)
		if found != null:
			return found
	return null


func _find_eyes(n: Node) -> MeshInstance3D:
	if n is MeshInstance3D and String(n.name).to_lower().contains("eyes"):
		var mi := n as MeshInstance3D
		if mi.mesh != null:
			return mi
	for ch in n.get_children():
		var found := _find_eyes(ch)
		if found != null:
			return found
	return null


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
