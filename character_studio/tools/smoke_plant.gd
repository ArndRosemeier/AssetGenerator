extends SceneTree
## Headless: leg length must not lift the character off the floor.


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var studio := (load("res://scenes/main.tscn") as PackedScene).instantiate()
	get_root().add_child(studio)
	await process_frame
	await process_frame

	for leg in [1.0, -1.0, 0.0]:
		var props: BodyProportions = studio.get_node("StudioUI").get_proportions().duplicate_props()
		props.leg_length = leg
		studio._on_proportions(props)
		await process_frame
		var body: Node3D = studio.get_node("Body")
		var skeleton := _find_skeleton(body)
		if skeleton == null:
			push_error("no skeleton")
			quit(1)
			return
		skeleton.force_update_all_bone_transforms()
		var sole := _lowest_sole_y(skeleton)
		print("smoke_plant leg_length=", leg, " sole_y=", sole, " body_y=", body.position.y)
		if is_nan(sole) or absf(sole) > 0.02:
			push_error("expected sole on the floor (y≈0), got %s" % sole)
			quit(1)
			return
	quit(0)


func _find_skeleton(n: Node) -> Skeleton3D:
	if n is Skeleton3D:
		return n as Skeleton3D
	for ch in n.get_children():
		var found := _find_skeleton(ch)
		if found != null:
			return found
	return null


func _lowest_sole_y(skel: Skeleton3D) -> float:
	var min_y := INF
	for bone_name: StringName in [&"ball_l", &"ball_r", &"foot_l", &"foot_r"]:
		var idx := skel.find_bone(String(bone_name))
		if idx < 0:
			continue
		min_y = minf(min_y, skel.to_global(skel.get_bone_global_pose(idx).origin).y)
	return min_y if min_y != INF else NAN
