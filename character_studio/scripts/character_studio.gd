## Focused front-facing character editor (modular body + garments + face morphs).
extends Node3D

const StudioUIScript := preload("res://scripts/studio_ui.gd")
const ProportionModifierScript := preload("res://scripts/proportion_modifier.gd")

var _female: bool = false
## slot -> asset id; empty string means the slot is unequipped (None).
var _selection: Dictionary = {
	"suit": "",
	"shoes": "",
	"hair": "",
	"eyebrows": "",
}
var _props: BodyProportions = BodyProportions.identity()
var _catalog: WardrobeCatalog
var _body_path: String = ""
var _body_root: Node3D
var _skeleton: Skeleton3D
var _prop_mod: ProportionModifier
var _ui: StudioUI

var _pivot: Node3D
var _camera: Camera3D
var _yaw: float = 0.0
var _pitch: float = 0.08
var _distance: float = 3.9
var _look_height: float = 0.85
var _dragging: bool = false
var _framing: StringName = &"body"


func _ready() -> void:
	_build_environment()
	_build_camera_rig()
	_catalog = WardrobeCatalog.load_default()
	## Open dressed, with hair + eyebrows, so the full modular stack is visible.
	_selection = {
		"suit": _catalog.first_id(_female, "suit"),
		"shoes": _catalog.first_id(_female, "shoes"),
		"hair": _default_hair(_female),
		"eyebrows": _catalog.first_id(_female, "eyebrows"),
	}
	_ui = StudioUIScript.new()
	_ui.name = "StudioUI"
	_ui.set_catalog(_catalog)
	add_child(_ui)
	_ui.set_wardrobe(_selection)
	_ui.proportions_changed.connect(_on_proportions)
	_ui.sex_change_requested.connect(_on_sex)
	_ui.wardrobe_changed.connect(_on_wardrobe)
	_ui.framing_requested.connect(_on_framing)
	_rebuild_character()
	_apply_framing(&"body")
	_update_camera()


func _build_environment() -> void:
	var world_env := WorldEnvironment.new()
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color(0.14, 0.15, 0.18)
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color(0.42, 0.45, 0.5)
	environment.ambient_light_energy = 0.65
	world_env.environment = environment
	add_child(world_env)

	var key := DirectionalLight3D.new()
	key.rotation_degrees = Vector3(-35.0, 40.0, 0.0)
	key.light_energy = 1.35
	key.shadow_enabled = true
	add_child(key)

	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-15.0, -120.0, 0.0)
	fill.light_energy = 0.4
	add_child(fill)

	var floor_mesh := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(8.0, 8.0)
	floor_mesh.mesh = plane
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.18, 0.19, 0.22)
	mat.roughness = 0.92
	floor_mesh.material_override = mat
	add_child(floor_mesh)


func _build_camera_rig() -> void:
	_pivot = Node3D.new()
	_pivot.name = "CameraPivot"
	add_child(_pivot)
	_camera = Camera3D.new()
	_camera.fov = 28.0
	_camera.current = true
	_pivot.add_child(_camera)


## Reloads the body only when the suit changed; other slots are swapped in place.
func _rebuild_character() -> void:
	var wanted_body := _catalog.body_path(_female, String(_selection.get("suit", "")))
	if wanted_body.is_empty():
		return
	if wanted_body != _body_path or _body_root == null or not is_instance_valid(_body_root):
		_spawn_body(wanted_body)
	_apply_wardrobe()
	_apply_proportions()


func _spawn_body(path: String) -> void:
	if _body_root != null and is_instance_valid(_body_root):
		_body_root.queue_free()
	_body_root = null
	_skeleton = null
	_prop_mod = null
	_body_path = ""

	if not ResourceLoader.exists(path):
		push_error("CharacterStudio: missing asset %s" % path)
		return
	var packed := load(path)
	if not (packed is PackedScene):
		push_error("CharacterStudio: %s is not a PackedScene" % path)
		return

	var instance := (packed as PackedScene).instantiate() as Node3D
	instance.name = "Body"
	## Face the camera: MH/glTF faces +Z; camera starts on +Z looking inward.
	instance.rotation.y = 0.0
	add_child(instance)
	_body_root = instance
	_body_path = path
	_skeleton = _find_skeleton(instance)
	if _skeleton == null:
		push_error("CharacterStudio: %s has no Skeleton3D" % path)
		return
	_prop_mod = ProportionModifierScript.new()
	_prop_mod.name = "ProportionModifier"
	_skeleton.add_child(_prop_mod)
	print("CharacterStudio body ", path, " face_morphs=", _count_face_morphs(instance))


func _apply_wardrobe() -> void:
	if _body_root == null or _skeleton == null:
		return
	ModularAssembler.clear(_body_root)
	var paths: Array[String] = []
	for slot: String in ["suit", "shoes", "hair", "eyebrows"]:
		var path := _catalog.path_for(_female, slot, String(_selection.get(slot, "")))
		if not path.is_empty():
			paths.append(path)
	var attached := ModularAssembler.attach(_body_root, _skeleton, paths)
	print(
		"CharacterStudio wardrobe",
		" suit=", _selection.get("suit", ""),
		" shoes=", _selection.get("shoes", ""),
		" hair=", _selection.get("hair", ""),
		" eyebrows=", _selection.get("eyebrows", ""),
		" meshes=", attached
	)


func _apply_proportions() -> void:
	if _props == null:
		_props = BodyProportions.identity()
	if _body_root != null:
		_props.apply_to_node(_body_root)
		var s := _props.body_uniform_scale()
		_body_root.scale = Vector3(s, s, s)
		## Measure soles from the authored placement, then re-plant.
		_body_root.position.y = 0.0
	if _prop_mod != null:
		_prop_mod.set_proportions(_props)
	_plant_feet_on_floor()


## Shift the body so the lowest sole sits on the floor plane at Y=0.
func _plant_feet_on_floor() -> void:
	if _body_root == null or _skeleton == null:
		return
	if not is_instance_valid(_body_root) or not is_instance_valid(_skeleton):
		return
	_skeleton.force_update_all_bone_transforms()
	var sole_y := _lowest_sole_world_y()
	if is_nan(sole_y):
		return
	_body_root.position.y = -sole_y


func _lowest_sole_world_y() -> float:
	## Prefer toe bones; mesh AABBs are rest-pose only and ignore bone scale.
	var min_y := INF
	var found := false
	for bone_name: StringName in [&"ball_l", &"ball_r", &"foot_l", &"foot_r"]:
		var idx := _skeleton.find_bone(String(bone_name))
		if idx < 0:
			continue
		var world := _skeleton.to_global(_skeleton.get_bone_global_pose(idx).origin)
		min_y = minf(min_y, world.y)
		found = true
	return min_y if found else NAN


func _on_proportions(props: BodyProportions) -> void:
	_props = props.duplicate_props()
	_apply_proportions()


func _on_sex(female: bool) -> void:
	_female = female
	## Remap each filled slot onto the new sex; suits are sex-specific, the rest
	## keep their id when the same asset exists for both bodies.
	var next: Dictionary = {}
	for slot: String in ["suit", "shoes", "hair", "eyebrows"]:
		var current := String(_selection.get(slot, ""))
		if current.is_empty():
			next[slot] = ""
			continue
		if not _catalog.path_for(_female, slot, current).is_empty():
			next[slot] = current
		else:
			next[slot] = _catalog.first_id(_female, slot)
	_selection = next
	_ui.set_wardrobe(_selection)
	_rebuild_character()


func _on_wardrobe(selection: Dictionary) -> void:
	_selection = selection.duplicate()
	_rebuild_character()


func _default_hair(female: bool) -> String:
	var preferred := "bob01" if female else "short02"
	if not _catalog.path_for(female, "hair", preferred).is_empty():
		return preferred
	return _catalog.first_id(female, "hair")


func _on_framing(mode: StringName) -> void:
	_apply_framing(mode)


func _apply_framing(mode: StringName) -> void:
	_framing = mode
	_yaw = 0.0
	if mode == &"body":
		## Aim near mid-height and stand far enough that shoes stay in a 28° FOV.
		_pitch = 0.0
		_look_height = 0.85
		_distance = 3.9
	else:
		_pitch = 0.08
		_look_height = 1.48
		_distance = 1.15
	_update_camera()


func _update_camera() -> void:
	if _pivot == null or _camera == null:
		return
	_pivot.global_position = Vector3(0.0, _look_height, 0.0)
	_pivot.rotation = Vector3(_pitch, _yaw, 0.0)
	_camera.position = Vector3(0.0, 0.0, _distance)
	_camera.look_at(_pivot.global_position, Vector3.UP)


func _unhandled_input(event: InputEvent) -> void:
	var mb := event as InputEventMouseButton
	if mb != null:
		if mb.button_index == MOUSE_BUTTON_LEFT:
			_dragging = mb.pressed
			get_viewport().set_input_as_handled()
			return
		if mb.pressed and mb.button_index == MOUSE_BUTTON_WHEEL_UP:
			_distance = clampf(_distance * 0.9, 0.55, 5.0)
			_update_camera()
			get_viewport().set_input_as_handled()
			return
		if mb.pressed and mb.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			_distance = clampf(_distance * 1.1, 0.55, 5.0)
			_update_camera()
			get_viewport().set_input_as_handled()
			return

	var mm := event as InputEventMouseMotion
	if mm != null and _dragging:
		_yaw -= mm.relative.x * 0.005
		_pitch = clampf(_pitch - mm.relative.y * 0.005, -0.35, 0.55)
		_update_camera()
		get_viewport().set_input_as_handled()


func _find_skeleton(root: Node) -> Skeleton3D:
	if root is Skeleton3D:
		return root as Skeleton3D
	for child in root.get_children():
		var found := _find_skeleton(child)
		if found != null:
			return found
	return null


func _count_face_morphs(root: Node) -> int:
	var best := 0
	if root is MeshInstance3D:
		var mesh := (root as MeshInstance3D).mesh as ArrayMesh
		if mesh != null:
			var n := 0
			for i in range(mesh.get_blend_shape_count()):
				if String(mesh.get_blend_shape_name(i)).begins_with("face_"):
					n += 1
			best = n
	for child in root.get_children():
		best = maxi(best, _count_face_morphs(child))
	return best
