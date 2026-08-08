## Player/NPC body proportions. Blend shapes when present; otherwise skeleton scales.
## Face sliders drive bipolar MPFB morph pairs named `<key>__pos` / `<key>__neg`.
class_name BodyProportions
extends RefCounted

const MORPH_HEIGHT := "height"
const MORPH_WEIGHT := "weight"
const MORPH_TORSO := "torso_length"
const MORPH_LEGS := "leg_length"
const MORPH_SHOULDERS := "shoulder_width"

## Face slider keys — must match tools/mpfb_face_morphs.py FACE_SLIDERS.
const FACE_KEYS: Array[String] = [
	"face_head_width",
	"face_head_depth",
	"face_forehead",
	"face_brow_height",
	"face_eye_size",
	"face_eye_spacing",
	"face_nose_width",
	"face_nose_length",
	"face_nose_tip",
	"face_cheekbones",
	"face_jaw_width",
	"face_chin",
	"face_mouth_width",
	"face_lip_fullness",
]

## Normalized params in roughly [-1, 1]. 0 = authored rest.
var height: float = 0.0
var weight: float = 0.0
var muscle: float = 0.0
var torso_length: float = 0.0
var leg_length: float = 0.0
var arm_length: float = 0.0
var shoulder_width: float = 0.0
var hip_width: float = 0.0
var head_size: float = 0.0
var neck_length: float = 0.0
var hand_size: float = 0.0
var foot_size: float = 0.0

var face_head_width: float = 0.0
var face_head_depth: float = 0.0
var face_forehead: float = 0.0
var face_brow_height: float = 0.0
var face_eye_size: float = 0.0
var face_eye_spacing: float = 0.0
var face_nose_width: float = 0.0
var face_nose_length: float = 0.0
var face_nose_tip: float = 0.0
var face_cheekbones: float = 0.0
var face_jaw_width: float = 0.0
var face_chin: float = 0.0
var face_mouth_width: float = 0.0
var face_lip_fullness: float = 0.0


static func identity() -> BodyProportions:
	return BodyProportions.new()


static func random(rng: RandomNumberGenerator) -> BodyProportions:
	var p := BodyProportions.new()
	p.height = rng.randf_range(-0.55, 0.65)
	p.weight = rng.randf_range(-0.55, 0.75)
	p.muscle = rng.randf_range(-0.45, 0.7)
	p.torso_length = rng.randf_range(-0.45, 0.45)
	p.leg_length = rng.randf_range(-0.45, 0.5)
	p.arm_length = rng.randf_range(-0.4, 0.45)
	p.shoulder_width = rng.randf_range(-0.45, 0.55)
	p.hip_width = rng.randf_range(-0.4, 0.5)
	p.head_size = rng.randf_range(-0.35, 0.4)
	p.neck_length = rng.randf_range(-0.35, 0.4)
	p.hand_size = rng.randf_range(-0.35, 0.4)
	p.foot_size = rng.randf_range(-0.35, 0.4)
	p.face_head_width = rng.randf_range(-0.55, 0.55)
	p.face_head_depth = rng.randf_range(-0.45, 0.45)
	p.face_forehead = rng.randf_range(-0.5, 0.5)
	p.face_brow_height = rng.randf_range(-0.5, 0.5)
	p.face_eye_size = rng.randf_range(-0.55, 0.55)
	p.face_eye_spacing = rng.randf_range(-0.5, 0.5)
	p.face_nose_width = rng.randf_range(-0.6, 0.6)
	p.face_nose_length = rng.randf_range(-0.55, 0.55)
	p.face_nose_tip = rng.randf_range(-0.5, 0.5)
	p.face_cheekbones = rng.randf_range(-0.55, 0.55)
	p.face_jaw_width = rng.randf_range(-0.55, 0.55)
	p.face_chin = rng.randf_range(-0.55, 0.55)
	p.face_mouth_width = rng.randf_range(-0.5, 0.5)
	p.face_lip_fullness = rng.randf_range(-0.55, 0.55)
	return p


func duplicate_props() -> BodyProportions:
	var p := BodyProportions.new()
	p.height = height
	p.weight = weight
	p.muscle = muscle
	p.torso_length = torso_length
	p.leg_length = leg_length
	p.arm_length = arm_length
	p.shoulder_width = shoulder_width
	p.hip_width = hip_width
	p.head_size = head_size
	p.neck_length = neck_length
	p.hand_size = hand_size
	p.foot_size = foot_size
	p.face_head_width = face_head_width
	p.face_head_depth = face_head_depth
	p.face_forehead = face_forehead
	p.face_brow_height = face_brow_height
	p.face_eye_size = face_eye_size
	p.face_eye_spacing = face_eye_spacing
	p.face_nose_width = face_nose_width
	p.face_nose_length = face_nose_length
	p.face_nose_tip = face_nose_tip
	p.face_cheekbones = face_cheekbones
	p.face_jaw_width = face_jaw_width
	p.face_chin = face_chin
	p.face_mouth_width = face_mouth_width
	p.face_lip_fullness = face_lip_fullness
	return p


## Flat name → value, for a save file. Every slider is listed explicitly so a renamed field is a
## compile error here rather than a proportion that silently stops being saved.
func to_dict() -> Dictionary[String, float]:
	return {
		"height": height,
		"weight": weight,
		"muscle": muscle,
		"torso_length": torso_length,
		"leg_length": leg_length,
		"arm_length": arm_length,
		"shoulder_width": shoulder_width,
		"hip_width": hip_width,
		"head_size": head_size,
		"neck_length": neck_length,
		"hand_size": hand_size,
		"foot_size": foot_size,
		"face_head_width": face_head_width,
		"face_head_depth": face_head_depth,
		"face_forehead": face_forehead,
		"face_brow_height": face_brow_height,
		"face_eye_size": face_eye_size,
		"face_eye_spacing": face_eye_spacing,
		"face_nose_width": face_nose_width,
		"face_nose_length": face_nose_length,
		"face_nose_tip": face_nose_tip,
		"face_cheekbones": face_cheekbones,
		"face_jaw_width": face_jaw_width,
		"face_chin": face_chin,
		"face_mouth_width": face_mouth_width,
		"face_lip_fullness": face_lip_fullness,
	}


## Missing keys stay at the authored rest pose: an older save simply had fewer sliders.
static func from_dict(data: Dictionary) -> BodyProportions:
	var p := BodyProportions.new()
	p.height = float(data.get("height", 0.0))
	p.weight = float(data.get("weight", 0.0))
	p.muscle = float(data.get("muscle", 0.0))
	p.torso_length = float(data.get("torso_length", 0.0))
	p.leg_length = float(data.get("leg_length", 0.0))
	p.arm_length = float(data.get("arm_length", 0.0))
	p.shoulder_width = float(data.get("shoulder_width", 0.0))
	p.hip_width = float(data.get("hip_width", 0.0))
	p.head_size = float(data.get("head_size", 0.0))
	p.neck_length = float(data.get("neck_length", 0.0))
	p.hand_size = float(data.get("hand_size", 0.0))
	p.foot_size = float(data.get("foot_size", 0.0))
	p.face_head_width = float(data.get("face_head_width", 0.0))
	p.face_head_depth = float(data.get("face_head_depth", 0.0))
	p.face_forehead = float(data.get("face_forehead", 0.0))
	p.face_brow_height = float(data.get("face_brow_height", 0.0))
	p.face_eye_size = float(data.get("face_eye_size", 0.0))
	p.face_eye_spacing = float(data.get("face_eye_spacing", 0.0))
	p.face_nose_width = float(data.get("face_nose_width", 0.0))
	p.face_nose_length = float(data.get("face_nose_length", 0.0))
	p.face_nose_tip = float(data.get("face_nose_tip", 0.0))
	p.face_cheekbones = float(data.get("face_cheekbones", 0.0))
	p.face_jaw_width = float(data.get("face_jaw_width", 0.0))
	p.face_chin = float(data.get("face_chin", 0.0))
	p.face_mouth_width = float(data.get("face_mouth_width", 0.0))
	p.face_lip_fullness = float(data.get("face_lip_fullness", 0.0))
	return p


func reset() -> void:
	height = 0.0
	weight = 0.0
	muscle = 0.0
	torso_length = 0.0
	leg_length = 0.0
	arm_length = 0.0
	shoulder_width = 0.0
	hip_width = 0.0
	head_size = 0.0
	neck_length = 0.0
	hand_size = 0.0
	foot_size = 0.0
	face_head_width = 0.0
	face_head_depth = 0.0
	face_forehead = 0.0
	face_brow_height = 0.0
	face_eye_size = 0.0
	face_eye_spacing = 0.0
	face_nose_width = 0.0
	face_nose_length = 0.0
	face_nose_tip = 0.0
	face_cheekbones = 0.0
	face_jaw_width = 0.0
	face_chin = 0.0
	face_mouth_width = 0.0
	face_lip_fullness = 0.0


## Uniform body scale from height slider (applied on the body root Node3D).
func body_uniform_scale() -> float:
	return _scale_factor(height, 0.18)


func capsule_height(base: float = 1.7) -> float:
	return base * body_uniform_scale() * _scale_factor(leg_length, 0.08) * _scale_factor(torso_length, 0.06)


func capsule_radius(base: float = 0.35) -> float:
	return base * _scale_factor(weight, 0.14) * _scale_factor(hip_width, 0.06)


func apply_to_mesh(mesh_instance: MeshInstance3D) -> void:
	if mesh_instance == null or mesh_instance.mesh == null:
		return
	_set_blend(mesh_instance, MORPH_HEIGHT, height)
	_set_blend(mesh_instance, MORPH_WEIGHT, weight)
	_set_blend(mesh_instance, MORPH_TORSO, torso_length)
	_set_blend(mesh_instance, MORPH_LEGS, leg_length)
	_set_blend(mesh_instance, MORPH_SHOULDERS, shoulder_width)
	for key in FACE_KEYS:
		_set_bipolar_blend(mesh_instance, key, float(get(key)))


## Apply morphs to every MeshInstance3D under root (outfit skin meshes carry face keys).
func apply_to_node(root: Node) -> void:
	if root == null:
		return
	if root is MeshInstance3D:
		apply_to_mesh(root as MeshInstance3D)
	for child in root.get_children():
		apply_to_node(child)


## Bone name → local pose scale. MPFB game_engine names (no City retarget map).
func bone_scales() -> Dictionary:
	var w_xz := _scale_factor(weight, 0.12)
	var muscle_xz := _scale_factor(muscle, 0.1)
	var torso_y := _scale_factor(torso_length, 0.14)
	var leg_y := _scale_factor(leg_length, 0.16)
	var arm_y := _scale_factor(arm_length, 0.14)
	var shoulder := _scale_factor(shoulder_width, 0.16)
	var hips := _scale_factor(hip_width, 0.14)
	var head := _scale_factor(head_size, 0.16)
	var neck_y := _scale_factor(neck_length, 0.18)
	var hand := _scale_factor(hand_size, 0.18)
	var foot := _scale_factor(foot_size, 0.18)
	var torso_xz := w_xz * muscle_xz
	return {
		&"pelvis": Vector3(hips * w_xz, 1.0, hips * w_xz),
		&"spine_01": Vector3(torso_xz, torso_y, torso_xz),
		&"spine_02": Vector3(torso_xz, torso_y, torso_xz),
		&"spine_03": Vector3(torso_xz * shoulder, torso_y, torso_xz),
		&"neck_01": Vector3(1.0, neck_y, 1.0),
		&"head": Vector3(head, head, head),
		&"clavicle_l": Vector3(shoulder, 1.0, shoulder),
		&"clavicle_r": Vector3(shoulder, 1.0, shoulder),
		&"upperarm_l": Vector3(muscle_xz, arm_y, muscle_xz),
		&"upperarm_r": Vector3(muscle_xz, arm_y, muscle_xz),
		&"lowerarm_l": Vector3(1.0, arm_y, 1.0),
		&"lowerarm_r": Vector3(1.0, arm_y, 1.0),
		&"hand_l": Vector3(hand, hand, hand),
		&"hand_r": Vector3(hand, hand, hand),
		&"thigh_l": Vector3(w_xz, leg_y, w_xz),
		&"thigh_r": Vector3(w_xz, leg_y, w_xz),
		&"calf_l": Vector3(1.0, leg_y, 1.0),
		&"calf_r": Vector3(1.0, leg_y, 1.0),
		&"foot_l": Vector3(foot, foot, foot),
		&"foot_r": Vector3(foot, foot, foot),
	}


func _scale_factor(value: float, amount: float) -> float:
	return 1.0 + clampf(value, -1.0, 1.0) * amount


func _set_blend(mesh_instance: MeshInstance3D, morph_name: String, value: float) -> void:
	# Godot blend shapes are typically [0, 1]; map [-1,1] -> [0,1] around 0.5 rest.
	var weight_01 := clampf(0.5 + value * 0.5, 0.0, 1.0)
	_set_blend_01(mesh_instance, morph_name, weight_01)


func _set_bipolar_blend(mesh_instance: MeshInstance3D, key: String, value: float) -> void:
	var v := clampf(value, -1.0, 1.0)
	_set_blend_01(mesh_instance, "%s__pos" % key, maxf(v, 0.0))
	_set_blend_01(mesh_instance, "%s__neg" % key, maxf(-v, 0.0))


func _set_blend_01(mesh_instance: MeshInstance3D, morph_name: String, weight_01: float) -> void:
	var idx := _find_blend_shape_index(mesh_instance, morph_name)
	if idx >= 0:
		mesh_instance.set_blend_shape_value(idx, clampf(weight_01, 0.0, 1.0))


func _find_blend_shape_index(mesh_instance: MeshInstance3D, morph_name: String) -> int:
	var mesh := mesh_instance.mesh as ArrayMesh
	if mesh == null:
		return -1
	for i in range(mesh.get_blend_shape_count()):
		if String(mesh.get_blend_shape_name(i)) == morph_name:
			return i
	return -1
