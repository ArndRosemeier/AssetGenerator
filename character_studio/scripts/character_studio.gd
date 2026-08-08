## Focused front-facing character editor (body + face morphs).
extends Node3D

const MALE_BASE := "res://assets/humans/male_base.glb"
const FEMALE_BASE := "res://assets/humans/female_base.glb"
const MALE_OUTFIT := "res://assets/humans/outfits/male_casual_01.glb"
const FEMALE_OUTFIT := "res://assets/humans/outfits/female_casual_01.glb"

const StudioUIScript := preload("res://scripts/studio_ui.gd")
const ProportionModifierScript := preload("res://scripts/proportion_modifier.gd")

var _female: bool = false
var _use_outfit: bool = true
var _props: BodyProportions = BodyProportions.identity()
var _body_root: Node3D
var _skeleton: Skeleton3D
var _prop_mod: ProportionModifier
var _ui: StudioUI

var _pivot: Node3D
var _camera: Camera3D
var _yaw: float = 0.0
var _pitch: float = 0.08
var _distance: float = 1.15
var _look_height: float = 1.48
var _dragging: bool = false
var _framing: StringName = &"face"


func _ready() -> void:
	_build_environment()
	_build_camera_rig()
	_ui = StudioUIScript.new()
	_ui.name = "StudioUI"
	add_child(_ui)
	_ui.proportions_changed.connect(_on_proportions)
	_ui.sex_change_requested.connect(_on_sex)
	_ui.outfit_change_requested.connect(_on_outfit)
	_ui.framing_requested.connect(_on_framing)
	_spawn_body()
	_apply_framing(&"face")
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


func _spawn_body() -> void:
	if _body_root != null and is_instance_valid(_body_root):
		_body_root.queue_free()
	_body_root = null
	_skeleton = null
	_prop_mod = null

	var path := _resolve_path()
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
	_skeleton = _find_skeleton(instance)
	if _skeleton != null:
		_prop_mod = ProportionModifierScript.new()
		_prop_mod.name = "ProportionModifier"
		_skeleton.add_child(_prop_mod)
	_apply_proportions()
	print("CharacterStudio loaded ", path, " face_morphs=", _count_face_morphs(instance))


func _resolve_path() -> String:
	if _use_outfit:
		return FEMALE_OUTFIT if _female else MALE_OUTFIT
	return FEMALE_BASE if _female else MALE_BASE


func _apply_proportions() -> void:
	if _props == null:
		_props = BodyProportions.identity()
	if _body_root != null:
		_props.apply_to_node(_body_root)
		var s := _props.body_uniform_scale()
		_body_root.scale = Vector3(s, s, s)
	if _prop_mod != null:
		_prop_mod.set_proportions(_props)


func _on_proportions(props: BodyProportions) -> void:
	_props = props.duplicate_props()
	_apply_proportions()


func _on_sex(female: bool) -> void:
	_female = female
	_spawn_body()


func _on_outfit(use_outfit: bool) -> void:
	_use_outfit = use_outfit
	_spawn_body()


func _on_framing(mode: StringName) -> void:
	_apply_framing(mode)


func _apply_framing(mode: StringName) -> void:
	_framing = mode
	_yaw = 0.0
	_pitch = 0.08
	if mode == &"body":
		_look_height = 0.95
		_distance = 2.6
	else:
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
