## Applies BodyProportions bone scales after AnimationPlayer each frame.
class_name ProportionModifier
extends SkeletonModifier3D

var proportions: BodyProportions = BodyProportions.identity()


func set_proportions(props: BodyProportions) -> void:
	proportions = props if props != null else BodyProportions.identity()


func _process_modification_with_delta(_delta: float) -> void:
	var skel := get_skeleton()
	if skel == null or proportions == null:
		return
	var scales: Dictionary = proportions.bone_scales()
	for bone_name: Variant in scales.keys():
		var idx := skel.find_bone(String(bone_name))
		if idx < 0:
			continue
		var s: Vector3 = scales[bone_name]
		var current := skel.get_bone_pose_scale(idx)
		skel.set_bone_pose_scale(idx, current * s)
