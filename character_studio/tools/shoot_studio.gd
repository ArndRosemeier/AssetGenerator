extends SceneTree
## Renders the studio in a few wardrobe configurations and writes PNGs.
##
## Needs a real window (no --headless). Output dir defaults to user://studio_shots
## and can be overridden with `-- --out=C:/somewhere`.

## "look"/"dist" override the body framing; feet need their own close-up because
## the bodies carry no shoe mask.
const SHOTS: Array[Dictionary] = [
	{
		"name": "male_casual",
		"female": false,
		"suit": "male_casualsuit01",
		"shoes": "shoes01",
		"hair": "short02",
		"eyebrows": "eyebrow001",
	},
	{
		"name": "male_elegant",
		"female": false,
		"suit": "male_elegantsuit01",
		"shoes": "shoes03",
		"hair": "short01",
		"eyebrows": "eyebrow003",
	},
	{
		"name": "male_bald_no_brows",
		"female": false,
		"suit": "male_casualsuit01",
		"shoes": "shoes01",
		"hair": "",
		"eyebrows": "",
	},
	{
		"name": "female_casual",
		"female": true,
		"suit": "female_casualsuit01",
		"shoes": "shoes01",
		"hair": "bob01",
		"eyebrows": "eyebrow002",
	},
	{
		"name": "female_sport",
		"female": true,
		"suit": "female_sportsuit01",
		"shoes": "shoes02",
		"hair": "ponytail01",
		"eyebrows": "eyebrow001",
	},
	{
		"name": "female_long",
		"female": true,
		"suit": "female_elegantsuit01",
		"shoes": "shoes03",
		"hair": "long01",
		"eyebrows": "eyebrow004",
	},
	{
		"name": "male_face",
		"female": false,
		"suit": "male_casualsuit01",
		"shoes": "shoes01",
		"hair": "short02",
		"eyebrows": "eyebrow001",
		"frame": "face",
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
		studio._on_wardrobe(
			{
				"suit": String(shot.get("suit", "")),
				"shoes": String(shot.get("shoes", "")),
				"hair": String(shot.get("hair", "")),
				"eyebrows": String(shot.get("eyebrows", "")),
			}
		)
		var frame := StringName(shot.get("frame", "body"))
		studio._apply_framing(frame)
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
