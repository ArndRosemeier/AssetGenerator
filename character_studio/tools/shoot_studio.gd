extends SceneTree
## Renders the studio in a few wardrobe configurations and writes PNGs.
##
## Needs a real window (no --headless). Output dir defaults to user://studio_shots
## and can be overridden with `-- --out=C:/somewhere`.

## "look"/"dist" override the body framing; feet need their own close-up because
## the bodies carry no shoe mask.
const SHOTS: Array[Dictionary] = [
	{"name": "male_casual", "female": false, "suit": "male_casualsuit01", "shoes": "shoes01"},
	{"name": "male_elegant", "female": false, "suit": "male_elegantsuit01", "shoes": "shoes03"},
	{"name": "male_work", "female": false, "suit": "male_worksuit01", "shoes": "shoes04"},
	{"name": "male_shoes_only", "female": false, "suit": "", "shoes": "shoes01"},
	{"name": "male_nude", "female": false, "suit": "", "shoes": ""},
	{
		"name": "male_feet",
		"female": false,
		"suit": "male_casualsuit01",
		"shoes": "shoes01",
		"look": 0.35,
		"dist": 1.5,
	},
	{"name": "female_casual", "female": true, "suit": "female_casualsuit01", "shoes": "shoes01"},
	{"name": "female_sport", "female": true, "suit": "female_sportsuit01", "shoes": "shoes02"},
	{"name": "female_elegant", "female": true, "suit": "female_elegantsuit01", "shoes": "shoes03"},
	{
		"name": "female_feet",
		"female": true,
		"suit": "female_sportsuit01",
		"shoes": "shoes02",
		"look": 0.35,
		"dist": 1.5,
	},
	{
		"name": "male_barefoot",
		"female": false,
		"suit": "male_casualsuit01",
		"shoes": "",
		"look": 0.35,
		"dist": 1.5,
	},
]


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var out_dir := "user://studio_shots"
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--out="):
			out_dir = arg.trim_prefix("--out=")
	DirAccess.make_dir_recursive_absolute(out_dir)

	DisplayServer.window_set_size(Vector2i(720, 1000))
	var studio := (load("res://scenes/main.tscn") as PackedScene).instantiate()
	get_root().add_child(studio)
	studio.get_node("StudioUI").visible = false
	await process_frame

	for shot in SHOTS:
		studio._female = bool(shot["female"])
		studio._on_wardrobe(String(shot["suit"]), String(shot["shoes"]))
		studio._apply_framing(&"body")
		if shot.has("look"):
			studio._look_height = float(shot["look"])
			studio._distance = float(shot["dist"])
			studio._update_camera()
		for i in range(6):
			await process_frame
		await RenderingServer.frame_post_draw
		var image := get_root().get_texture().get_image()
		var path := "%s/%s.png" % [out_dir, shot["name"]]
		var err := image.save_png(path)
		if err != OK:
			push_error("could not write %s (%d)" % [path, err])
			quit(1)
			return
		print("shot ", path)
	quit(0)
