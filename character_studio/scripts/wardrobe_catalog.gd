## Reads assets/humans/wardrobe.json, the catalogue the Blender export writes.
##
## There is a nude body per sex plus one body per suit, whose skin under exactly
## that suit has been deleted. Shoes never mask the body, so they fit any of them.
class_name WardrobeCatalog
extends RefCounted

const CATALOG_PATH := "res://assets/humans/wardrobe.json"

var slots: Array[String] = []
## sex -> {"nude": String, "dressed": {suit_id: String}}
var _bodies: Dictionary = {}
var _items: Array[Dictionary] = []


static func load_default() -> WardrobeCatalog:
	var catalog := WardrobeCatalog.new()
	catalog.load_from(CATALOG_PATH)
	return catalog


func load_from(path: String) -> void:
	if not FileAccess.file_exists(path):
		push_error("WardrobeCatalog: missing %s — run tools/sync_character_studio_assets.py" % path)
		return
	var text := FileAccess.get_file_as_string(path)
	var parsed: Variant = JSON.parse_string(text)
	if not (parsed is Dictionary):
		push_error("WardrobeCatalog: %s is not a JSON object" % path)
		return
	var data: Dictionary = parsed

	slots.clear()
	for slot: Variant in data.get("slots", []):
		slots.append(String(slot))

	_bodies.clear()
	for entry: Variant in data.get("bodies", []):
		var body: Dictionary = entry
		var dressed: Dictionary = {}
		for suit_id: Variant in (body["dressed"] as Dictionary):
			dressed[String(suit_id)] = String((body["dressed"] as Dictionary)[suit_id])
		_bodies[String(body["sex"])] = {"nude": String(body["nude"]), "dressed": dressed}

	_items.clear()
	for entry: Variant in data.get("items", []):
		var item: Dictionary = entry
		_items.append(
			{
				"id": String(item["id"]),
				"sex": String(item["sex"]),
				"slot": String(item["slot"]),
				"label": String(item["label"]),
				"path": String(item["path"]),
			}
		)


func is_empty() -> bool:
	return _items.is_empty()


## The body to spawn under a given suit; the nude one when no suit is worn.
func body_path(female: bool, suit_id: String) -> String:
	var sex := "female" if female else "male"
	if not _bodies.has(sex):
		push_error("WardrobeCatalog: no body entry for %s" % sex)
		return ""
	var entry: Dictionary = _bodies[sex]
	if suit_id.is_empty():
		return String(entry["nude"])
	var dressed: Dictionary = entry["dressed"]
	if not dressed.has(suit_id):
		push_error("WardrobeCatalog: no %s body for suit %s" % [sex, suit_id])
		return ""
	return String(dressed[suit_id])


## Garments for one sex and slot, in catalogue order.
func items_for(female: bool, slot: String) -> Array[Dictionary]:
	var sex := "female" if female else "male"
	var out: Array[Dictionary] = []
	for item in _items:
		if item["sex"] == sex and item["slot"] == slot:
			out.append(item)
	return out


func path_for(female: bool, slot: String, id: String) -> String:
	if id.is_empty():
		return ""
	for item in items_for(female, slot):
		if item["id"] == id:
			return String(item["path"])
	push_error("WardrobeCatalog: no %s item %s for %s" % [slot, id, "female" if female else "male"])
	return ""


## First garment of a slot, or "" when the slot is empty for this sex.
func first_id(female: bool, slot: String) -> String:
	var items := items_for(female, slot)
	return String(items[0]["id"]) if not items.is_empty() else ""
