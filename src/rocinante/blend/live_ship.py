"""Persistent Blender scene and selection bridge. Runs inside the visible app."""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_ship import (
    add_lights,
    apply_materials,
    build_decks,
    build_drive,
    build_hull,
    build_pdcs,
    build_tubes,
    frame_camera,
    frame_viewports,
)
from landmarks import build_landmark
from torpedoes import build_loaded_torpedoes

SPEC_PATH = Path(sys.argv[sys.argv.index("--") + 1])
SELECTION_PATH = SPEC_PATH.with_name("selection.json")
last_digest = None
last_rounds = None
last_request = None
animation = None
ship_span, ship_center = 50, (0, 0, 0)


def clear_live_scene():
    """Remove only generated scene data; retain the application and its viewports."""
    for obj in list(bpy.data.objects):
        startup_default = last_digest is None and "--factory-startup" in sys.argv and obj.name in {"Cube", "Camera", "Light"}
        if obj.get("rocinante_part") or obj.name in {"camera", "focus", "key", "rim"} or startup_default:
            bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def acknowledge(command, status, message):
    path = SPEC_PATH.with_name("blender-selection-status.json")
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps({"request_id": command["request_id"], "status": status, "message": message}))
    temp.replace(path)


def selection_objects(selection):
    kind, ident = selection["kind"], selection.get("id")
    if kind == "landmark":
        return build_landmark(ident)
    objects = list(bpy.context.scene.objects)
    if kind == "torpedo":
        return [o for o in objects if o.get("torpedo_id") == ident]
    if kind == "deck":
        return [o for o in objects if o.get("deck_index") == ident]
    if kind in {"crew", "part"}:
        return [o for o in objects if o.get("rocinante_part") == ident]
    return [o for o in objects if o.get("rocinante_part") and not o.get("torpedo_id")]


def focus(command):
    global animation
    # Stop an older transition even when the replacement cannot be resolved.
    animation = None
    selection = command.get("selection") or (
        {"kind": "torpedo", "id": command["torpedo_id"]} if command.get("torpedo_id") else {"kind": "ship"})
    objects = selection_objects(selection)
    if not objects:
        acknowledge(command, "error", "Selected model is not present in the Blender scene")
        return
    kind = selection["kind"]
    deck = objects[0].get("deck_index") if kind == "crew" else None
    for obj in list(bpy.context.selected_objects):
        obj.select_set(False)
    for obj in bpy.context.scene.objects:
        if not (obj.get("rocinante_part") or obj.get("landmark_id")):
            continue
        # Reset presentation transforms before applying the next selection.
        if "rocinante_base_location" not in obj:
            obj["rocinante_base_location"] = list(obj.location)
        obj.location = Vector(obj["rocinante_base_location"])
        if kind == "ship" and selection.get("expanded"):
            offset = obj.get("assembly_offset")
            if offset:
                obj.location += Vector((offset[0], -offset[2], offset[1]))
        visible = (not obj.get("landmark_id") if kind == "ship" else
                   obj in objects or (deck is not None and obj.get("deck_index") == deck))
        obj.hide_set(not visible)
    bpy.context.view_layer.update()
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    points = [obj.matrix_world @ Vector(c) for obj in objects if obj.type == "MESH" for c in obj.bound_box]
    lo = Vector(tuple(min(p[i] for p in points) for i in range(3)))
    hi = Vector(tuple(max(p[i] for p in points) for i in range(3)))
    center, distance = (lo + hi)/2, (hi-lo).length*1.8
    views = []
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                space = area.spaces.active
                space.clip_start = .001
                space.clip_end = max(30000, distance*4)
                region = space.region_3d
                region.view_perspective = "PERSP"
                direction = Vector((.7, 1 if center.y >= 0 else -1, .5)).to_track_quat("Z", "Y")
                views.append((area, region, region.view_location.copy(), region.view_distance, region.view_rotation.copy(), direction))
    animation = (time.monotonic(), center, max(.12, distance), views, command)


def animate():
    global animation
    if animation:
        started, center, distance, views, command = animation
        t = min(1, (time.monotonic()-started)/1.1)
        eased = t*t*t*(t*(6*t-15)+10)
        for area, region, origin, zoom, rotation, direction in views:
            region.view_location = origin.lerp(center, eased)
            region.view_distance = zoom+(distance-zoom)*eased
            region.view_rotation = rotation.slerp(direction, eased)
            area.tag_redraw()
        if t == 1:
            acknowledge(command, "synced", "Focused selected model")
            animation = None
    return .02


def refresh():
    global last_digest, last_rounds, last_request, ship_span, ship_center
    try:
        raw = SPEC_PATH.read_bytes()
        spec = json.loads(raw)
        try:
            command = json.loads(SELECTION_PATH.read_text())
        except FileNotFoundError:
            command = {"request_id": 0, "torpedo_id": None, "torpedoes": {}}
        digest = hashlib.sha256(raw).hexdigest()
        rounds = json.dumps([spec["torpedo"], command.get("torpedoes", {})], sort_keys=True)
        rebuilt = digest != last_digest
        if rebuilt:
            clear_live_scene()
            tubes = build_tubes(spec)
            objects = build_hull(spec) + build_drive(spec) + build_pdcs(spec) + tubes + build_decks(spec)
            apply_materials(objects)
            bpy.context.view_layer.update()
            ship_span, ship_center = frame_camera(objects)
            add_lights(ship_span, ship_center)
            if last_digest is None:
                frame_viewports(ship_span, ship_center)
            last_digest = digest
            bpy.context.scene["rocinante_spec_path"] = str(SPEC_PATH)
        if rebuilt or rounds != last_rounds:
            for obj in list(bpy.data.objects):
                if obj.get("torpedo_id"):
                    bpy.data.objects.remove(obj, do_unlink=True)
            tubes = [o for o in bpy.context.scene.objects if o.get("rocinante_part", "").startswith("tube_")]
            build_loaded_torpedoes(spec, tubes, command.get("torpedoes"))
            bpy.context.view_layer.update()
            last_rounds = rounds
        if rebuilt or command["request_id"] != last_request:
            focus(command)
            last_request = command["request_id"]
    except Exception as exc:  # noqa: BLE001 -- report a failed update without killing Blender
        print(f"Rocinante live scene: {exc}")
        if 'command' in locals():
            acknowledge(command, "error", str(exc))
    return .25


# Upgrade older live scripts too, whose timers predate the named registry.
import gc
import types

for callback in gc.get_objects():
    if (isinstance(callback, types.FunctionType) and callback.__name__ == "refresh"
            and callback.__code__.co_filename == str(Path(__file__).resolve())
            and bpy.app.timers.is_registered(callback)):
        bpy.app.timers.unregister(callback)
# Reloading this script replaces the bridge timers in the existing app.
for callback in bpy.app.driver_namespace.get("rocinante_timers", []):
    if bpy.app.timers.is_registered(callback):
        bpy.app.timers.unregister(callback)
bpy.context.preferences.view.show_splash = False
refresh()
bpy.app.timers.register(refresh, first_interval=.25, persistent=True)
bpy.app.timers.register(animate, first_interval=.02, persistent=True)
bpy.app.driver_namespace["rocinante_timers"] = [refresh, animate]
