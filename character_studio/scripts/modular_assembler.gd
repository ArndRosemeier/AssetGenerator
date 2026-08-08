## Binds separately exported garment meshes to the body's skeleton.
##
## Every piece GLB ships its own copy of the game_engine armature because glTF
## cannot store a skinned mesh without one. The export guarantees those copies
## are identical to the body's, so attaching a garment means moving its
## MeshInstance3D under the body Skeleton3D and dropping the duplicate armature.
class_name ModularAssembler
extends RefCounted

const PIECE_GROUP := &"ModularPiece"


static func clear(root: Node) -> void:
	for node in _collect_pieces(root):
		node.get_parent().remove_child(node)
		node.queue_free()


## Returns the number of garment meshes attached.
static func attach(body_root: Node3D, skeleton: Skeleton3D, piece_paths: Array[String]) -> int:
	if body_root == null or skeleton == null:
		push_error("ModularAssembler: body root and skeleton are required")
		return 0
	if not body_root.is_inside_tree():
		push_error("ModularAssembler: body root must be in the tree so transforms resolve")
		return 0

	var attached := 0
	for path in piece_paths:
		if path.is_empty():
			continue
		attached += _attach_one(body_root, skeleton, path)
	return attached


static func _attach_one(body_root: Node3D, skeleton: Skeleton3D, path: String) -> int:
	if not ResourceLoader.exists(path):
		push_error("ModularAssembler: missing piece %s" % path)
		return 0
	var packed := load(path)
	if not (packed is PackedScene):
		push_error("ModularAssembler: %s is not a PackedScene" % path)
		return 0

	var piece := (packed as PackedScene).instantiate() as Node3D
	# Parent first: global_transform is only meaningful inside the tree.
	body_root.add_child(piece)

	var piece_skeleton := _find_skeleton(piece)
	if piece_skeleton == null:
		push_error("ModularAssembler: %s has no Skeleton3D" % path)
		piece.queue_free()
		return 0

	var meshes := _collect_skinned_meshes(piece)
	if meshes.is_empty():
		push_error("ModularAssembler: %s has no skinned mesh" % path)
		piece.queue_free()
		return 0

	var attached := 0
	for mesh in meshes:
		var local := piece_skeleton.global_transform.affine_inverse() * mesh.global_transform
		mesh.get_parent().remove_child(mesh)
		skeleton.add_child(mesh)
		mesh.transform = local
		mesh.skeleton = NodePath("..")
		mesh.add_to_group(PIECE_GROUP)
		attached += 1

	piece.queue_free()
	return attached


static func _collect_pieces(root: Node) -> Array[Node]:
	var found: Array[Node] = []
	if root.is_in_group(PIECE_GROUP):
		found.append(root)
	for child in root.get_children():
		found.append_array(_collect_pieces(child))
	return found


static func _collect_skinned_meshes(root: Node) -> Array[MeshInstance3D]:
	var found: Array[MeshInstance3D] = []
	if root is MeshInstance3D:
		var mesh := root as MeshInstance3D
		if mesh.mesh != null and mesh.skin != null:
			found.append(mesh)
	for child in root.get_children():
		found.append_array(_collect_skinned_meshes(child))
	return found


static func _find_skeleton(root: Node) -> Skeleton3D:
	if root is Skeleton3D:
		return root as Skeleton3D
	for child in root.get_children():
		var found := _find_skeleton(child)
		if found != null:
			return found
	return null
