"""Visual QA of the actual exported GLB. Run with Blender --background --python."""
from pathlib import Path

import bpy
from mathutils import Vector

root = Path(__file__).resolve().parents[1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(root / "web/rocinante.glb"))
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.samples = 16
scene.cycles.use_denoising = True
scene.render.resolution_x = 960
scene.render.resolution_y = 720
scene.render.resolution_percentage = 100
scene.world = bpy.data.worlds.new("Room studio")
scene.world.use_nodes = True
scene.world.node_tree.nodes["Background"].inputs[0].default_value = (.055, .07, .09, 1)
scene.world.node_tree.nodes["Background"].inputs[1].default_value = .5
objects = list(scene.objects)
decks = sorted((o for o in objects if o.get("assembly_kind") == "deck"),
               key=lambda o: o["deck_index"])
camera = bpy.data.objects.new("Room camera", bpy.data.cameras.new("Room camera"))
scene.collection.objects.link(camera)
scene.camera = camera
camera.data.type = "ORTHO"
lights = []
for name, energy in (("Soft key", 1800), ("Cool fill", 1100)):
    data = bpy.data.lights.new(name, "AREA")
    data.energy, data.shape, data.size = energy, "DISK", 5
    light = bpy.data.objects.new(name, data)
    scene.collection.objects.link(light)
    lights.append(light)
output = root / "out/room-previews"
output.mkdir(parents=True, exist_ok=True)
for deck in decks:
    for obj in objects:
        obj.hide_render = obj.get("deck_index") != deck["deck_index"]
    points = [deck.matrix_world @ Vector(corner) for corner in deck.bound_box]
    center = sum(points, Vector()) / 8
    span = max(max(p[i] for p in points) - min(p[i] for p in points) for i in range(3))
    camera.location = center + Vector((span * .50, span * 1.3, span * .90))
    camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.ortho_scale = span * 1.35
    for light, offset in zip(lights, ((3, 4, 6), (-4, 1, 3))):
        light.location = center + Vector(offset)
        light.rotation_euler = (center - light.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = str(output / f"{deck['deck_index'] + 1:02d}.png")
    bpy.ops.render.render(write_still=True)
