## Applies BodyProportions bone scales.
##
## Character Studio has no AnimationMixer, so SkeletonModifier3D callbacks never
## fire. apply_now() is the real entry point; the modifier hooks stay as a
## fallback if an animation player is added later.
class_name ProportionModifier
extends SkeletonModifier3D

var proportions: BodyProportions = BodyProportions.identity()


func set_proportions(props: BodyProportions) -> void:
	proportions = props if props != null else BodyProportions.identity()
	apply_now()


## Write the current proportion scales onto the skeleton pose (absolute, not
## multiplied — the studio rest pose is always scale 1).
func apply_now() -> void:
	var skel := get_skeleton()
	if skel == null:
		skel = get_parent() as Skeleton3D
	if skel == null or proportions == null:
		return
	var scales: Dictionary = proportions.bone_scales()
	for bone_name: Variant in scales.keys():
		var idx := skel.find_bone(String(bone_name))
		if idx < 0:
			continue
		var s: Vector3 = scales[bone_name]
		skel.set_bone_pose_scale(idx, s)


func _process_modification() -> void:
	apply_now()


func _process_modification_with_delta(_delta: float) -> void:
	apply_now()
