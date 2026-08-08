## Left-side body/face slider panel for Character Studio.
class_name StudioUI
extends CanvasLayer

signal proportions_changed(props: BodyProportions)
signal sex_change_requested(female: bool)
signal outfit_change_requested(use_outfit: bool)
signal framing_requested(mode: StringName)

const BODY_SLIDERS: Array[Dictionary] = [
	{"key": "height", "label": "Height"},
	{"key": "weight", "label": "Weight"},
	{"key": "muscle", "label": "Muscle"},
	{"key": "torso_length", "label": "Torso length"},
	{"key": "leg_length", "label": "Leg length"},
	{"key": "arm_length", "label": "Arm length"},
	{"key": "shoulder_width", "label": "Shoulder width"},
	{"key": "hip_width", "label": "Hip width"},
	{"key": "head_size", "label": "Head size"},
	{"key": "neck_length", "label": "Neck length"},
	{"key": "hand_size", "label": "Hand size"},
	{"key": "foot_size", "label": "Foot size"},
]

const FACE_SLIDERS: Array[Dictionary] = [
	{"key": "face_head_width", "label": "Head width"},
	{"key": "face_head_depth", "label": "Head depth"},
	{"key": "face_forehead", "label": "Forehead"},
	{"key": "face_brow_height", "label": "Brow height"},
	{"key": "face_eye_size", "label": "Eye size"},
	{"key": "face_eye_spacing", "label": "Eye spacing"},
	{"key": "face_nose_width", "label": "Nose width"},
	{"key": "face_nose_length", "label": "Nose length"},
	{"key": "face_nose_tip", "label": "Nose tip"},
	{"key": "face_cheekbones", "label": "Cheekbones"},
	{"key": "face_jaw_width", "label": "Jaw width"},
	{"key": "face_chin", "label": "Chin"},
	{"key": "face_mouth_width", "label": "Mouth width"},
	{"key": "face_lip_fullness", "label": "Lip fullness"},
]

var _props: BodyProportions = BodyProportions.identity()
var _female: bool = false
var _use_outfit: bool = true
var _sex_label: Label
var _slider_by_key: Dictionary = {}
var _suppress: bool = false


func _ready() -> void:
	layer = 10
	_build_ui()
	_sync_sliders_from_props()
	_refresh_sex_label()


func get_proportions() -> BodyProportions:
	return _props


func set_state(props: BodyProportions, female: bool) -> void:
	_props = props.duplicate_props() if props != null else BodyProportions.identity()
	_female = female
	_sync_sliders_from_props()
	_refresh_sex_label()


func _build_ui() -> void:
	var panel := PanelContainer.new()
	panel.name = "Panel"
	panel.set_anchors_preset(Control.PRESET_LEFT_WIDE)
	panel.offset_left = 16.0
	panel.offset_top = 16.0
	panel.offset_right = 420.0
	panel.offset_bottom = -16.0
	add_child(panel)

	var margin := MarginContainer.new()
	margin.add_theme_constant_override("margin_left", 14)
	margin.add_theme_constant_override("margin_right", 14)
	margin.add_theme_constant_override("margin_top", 12)
	margin.add_theme_constant_override("margin_bottom", 12)
	panel.add_child(margin)

	var root := VBoxContainer.new()
	root.add_theme_constant_override("separation", 8)
	margin.add_child(root)

	var title := Label.new()
	title.text = "Character Studio"
	title.add_theme_font_size_override("font_size", 22)
	root.add_child(title)

	var hint := Label.new()
	hint.text = "Drag to orbit · Wheel zoom · Face-first preview"
	hint.modulate = Color(0.72, 0.76, 0.84)
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	root.add_child(hint)

	var sex_row := HBoxContainer.new()
	sex_row.add_theme_constant_override("separation", 8)
	root.add_child(sex_row)
	_sex_label = Label.new()
	_sex_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	sex_row.add_child(_sex_label)
	var male_btn := Button.new()
	male_btn.text = "Male"
	male_btn.pressed.connect(func() -> void: _request_sex(false))
	sex_row.add_child(male_btn)
	var female_btn := Button.new()
	female_btn.text = "Female"
	female_btn.pressed.connect(func() -> void: _request_sex(true))
	sex_row.add_child(female_btn)

	var outfit_row := HBoxContainer.new()
	outfit_row.add_theme_constant_override("separation", 8)
	root.add_child(outfit_row)
	var nude_btn := Button.new()
	nude_btn.text = "Nude base"
	nude_btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	nude_btn.pressed.connect(func() -> void: _request_outfit(false))
	outfit_row.add_child(nude_btn)
	var outfit_btn := Button.new()
	outfit_btn.text = "Casual outfit"
	outfit_btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	outfit_btn.pressed.connect(func() -> void: _request_outfit(true))
	outfit_row.add_child(outfit_btn)

	var frame_row := HBoxContainer.new()
	frame_row.add_theme_constant_override("separation", 8)
	root.add_child(frame_row)
	var face_btn := Button.new()
	face_btn.text = "Frame face"
	face_btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	face_btn.pressed.connect(func() -> void: framing_requested.emit(&"face"))
	frame_row.add_child(face_btn)
	var body_btn := Button.new()
	body_btn.text = "Frame body"
	body_btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	body_btn.pressed.connect(func() -> void: framing_requested.emit(&"body"))
	frame_row.add_child(body_btn)

	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	root.add_child(scroll)

	var list := VBoxContainer.new()
	list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	list.add_theme_constant_override("separation", 6)
	scroll.add_child(list)

	list.add_child(_section_label("Body"))
	for spec in BODY_SLIDERS:
		list.add_child(_make_slider_row(String(spec["key"]), String(spec["label"])))
	list.add_child(_section_label("Face"))
	for spec in FACE_SLIDERS:
		list.add_child(_make_slider_row(String(spec["key"]), String(spec["label"])))

	var actions := HBoxContainer.new()
	actions.add_theme_constant_override("separation", 8)
	root.add_child(actions)
	var random_btn := Button.new()
	random_btn.text = "Randomize"
	random_btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	random_btn.pressed.connect(_on_randomize)
	actions.add_child(random_btn)
	var reset_btn := Button.new()
	reset_btn.text = "Reset"
	reset_btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	reset_btn.pressed.connect(_on_reset)
	actions.add_child(reset_btn)


func _section_label(text: String) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", 16)
	label.modulate = Color(0.85, 0.88, 0.95)
	return label


func _make_slider_row(key: String, label_text: String) -> Control:
	var row := VBoxContainer.new()
	row.add_theme_constant_override("separation", 2)
	var top := HBoxContainer.new()
	row.add_child(top)
	var label := Label.new()
	label.text = label_text
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	top.add_child(label)
	var value_label := Label.new()
	value_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	value_label.custom_minimum_size = Vector2(48, 0)
	top.add_child(value_label)
	var slider := HSlider.new()
	slider.min_value = -1.0
	slider.max_value = 1.0
	slider.step = 0.01
	slider.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	slider.value_changed.connect(func(v: float) -> void: _on_slider(key, v, value_label))
	row.add_child(slider)
	_slider_by_key[key] = {"slider": slider, "value_label": value_label}
	return row


func _sync_sliders_from_props() -> void:
	_suppress = true
	for key: Variant in _slider_by_key.keys():
		var entry: Dictionary = _slider_by_key[key]
		var slider: HSlider = entry["slider"]
		var value_label: Label = entry["value_label"]
		var v: float = float(_props.get(String(key)))
		slider.value = v
		value_label.text = "%+.2f" % v
	_suppress = false


func _refresh_sex_label() -> void:
	_sex_label.text = "Body: Female" if _female else "Body: Male"


func _on_slider(key: String, value: float, value_label: Label) -> void:
	value_label.text = "%+.2f" % value
	if _suppress:
		return
	_props.set(key, value)
	proportions_changed.emit(_props)


func _on_randomize() -> void:
	var rng := RandomNumberGenerator.new()
	rng.randomize()
	_props = BodyProportions.random(rng)
	_sync_sliders_from_props()
	proportions_changed.emit(_props)


func _on_reset() -> void:
	_props.reset()
	_sync_sliders_from_props()
	proportions_changed.emit(_props)


func _request_sex(female: bool) -> void:
	if female == _female:
		return
	_female = female
	_refresh_sex_label()
	sex_change_requested.emit(_female)


func _request_outfit(use_outfit: bool) -> void:
	_use_outfit = use_outfit
	outfit_change_requested.emit(_use_outfit)
