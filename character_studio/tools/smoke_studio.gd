extends SceneTree
## Headless smoke: main scene loads and face morphs are present.


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
	print("smoke body_ok face_morphs=", face, " eyes=", eyes != null)
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
	quit(0)


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
