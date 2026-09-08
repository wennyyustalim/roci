"""Runs INSIDE Blender. Not importable from the host -- `bpy` only exists there.

    blender --background --factory-startup --python build_rocket.py -- payload.json

payload.json is {"spec": <RocketSpec dump>, "out": "x.glb"|null,
                 "render": {"path": ..., "resolution": [w, h]}|null}

Every mesh is tagged with a custom property `rocinante_part`. The web viewer keys
its diff highlighting off that name, so the two sides of a comparison line up
part by part instead of vertex by vertex.

STATUS: nose cone and body tubes build. Fins and the transition between tubes
of different radius are the morning's work.
"""

import json
import math
import sys

import bpy
import mathutils

PART = "rocinante_part"


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def tag(obj, part_name):
    obj[PART] = part_name
    obj.name = part_name


def nose_profile(shape, length, radius, param, steps=32):
    """Radius as a function of distance aft of the tip."""
    pts = []
    for i in range(steps + 1):
        x = length * i / steps
        f = x / length
        if shape == "conical":
            r = radius * f
        elif shape == "ellipsoid":
            r = radius * math.sqrt(max(0.0, 1 - (1 - f) ** 2))
        elif shape == "parabolic":
            r = radius * (2 * f - param * f * f) / (2 - param)
        elif shape == "haack":
            theta = math.acos(max(-1.0, min(1.0, 1 - 2 * f)))
            r = (radius / math.sqrt(math.pi)) * math.sqrt(
                theta - math.sin(2 * theta) / 2 + param * math.sin(theta) ** 3
            )
        else:  # tangent ogive
            rho = (radius**2 + length**2) / (2 * radius)
            r = math.sqrt(max(0.0, rho**2 - (length - x) ** 2)) + radius - rho
        pts.append((x, max(r, 1e-5)))
    return pts


def build_nose(spec, z_top):
    """Lathe the profile. Z runs down the body, +Z toward the nose."""
    nose = spec["nose"]
    profile = nose_profile(
        nose["shape"], nose["length_m"], nose["base_radius_m"], nose["shape_parameter"]
    )
    verts, faces = [], []
    segments = 32
    for x, r in profile:
        ring_start = len(verts)
        for s in range(segments):
            a = 2 * math.pi * s / segments
            verts.append((r * math.cos(a), r * math.sin(a), z_top - x))
        if ring_start:
            prev = ring_start - segments
            for s in range(segments):
                n = (s + 1) % segments
                faces.append((prev + s, prev + n, ring_start + n, ring_start + s))

    mesh = bpy.data.meshes.new("nose")
    mesh.from_pydata(verts, [], faces)
    mesh.validate()
    obj = bpy.data.objects.new("nose", mesh)
    bpy.context.collection.objects.link(obj)
    tag(obj, "nose")
    return obj


def build_tube(tube, index, z_top):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=32,
        radius=tube["outer_radius_m"],
        depth=tube["length_m"],
        location=(0, 0, z_top - tube["length_m"] / 2),
    )
    obj = bpy.context.active_object
    tag(obj, f"tube_{index}")
    return obj


def build_fins(spec, z_aft):
    """One trapezoid extruded to thickness, then copied around the body.

    Each fin is its own object named fin_0 .. fin_n, so the viewer can colour
    a single changed fin rather than the whole set.
    """
    fins = spec["fins"]
    r = spec["body"][-1]["outer_radius_m"]
    h = fins["height_m"]
    t = fins["thickness_m"] / 2

    root_te = z_aft + fins["offset_from_aft_m"]
    root_le = root_te + fins["root_chord_m"]
    tip_le = root_le - fins["sweep_m"]
    tip_te = tip_le - fins["tip_chord_m"]

    # Trapezoid in the XZ plane, then given thickness along Y.
    profile = [(r, root_te), (r, root_le), (r + h, tip_le), (r + h, tip_te)]
    verts = [(x, -t, z) for x, z in profile] + [(x, t, z) for x, z in profile]
    faces = [
        (0, 1, 2, 3),  # near face
        (7, 6, 5, 4),  # far face
        (0, 4, 5, 1),  # trailing edge
        (1, 5, 6, 2),  # leading edge
        (2, 6, 7, 3),  # tip
        (3, 7, 4, 0),  # root
    ]

    made = []
    for i in range(fins["count"]):
        mesh = bpy.data.meshes.new(f"fin_{i}")
        mesh.from_pydata(verts, [], faces)
        mesh.validate()
        obj = bpy.data.objects.new(f"fin_{i}", mesh)
        obj.rotation_euler = (0, 0, 2 * math.pi * i / fins["count"])
        bpy.context.collection.objects.link(obj)
        tag(obj, f"fin_{i}")
        made.append(obj)
    return made


def build_transition(lower, upper, z, index):
    """Cone between two tubes of different radius. `z` is the shared boundary."""
    if abs(lower["outer_radius_m"] - upper["outer_radius_m"]) < 1e-6:
        return None
    length = abs(lower["outer_radius_m"] - upper["outer_radius_m"]) * 1.5
    bpy.ops.mesh.primitive_cone_add(
        vertices=32,
        radius1=lower["outer_radius_m"],
        radius2=upper["outer_radius_m"],
        depth=length,
        location=(0, 0, z - length / 2),
    )
    obj = bpy.context.active_object
    tag(obj, f"transition_{index}")
    return obj


def build_rocket(spec):
    clear_scene()
    total = spec["nose"]["length_m"] + sum(t["length_m"] for t in spec["body"])
    z = total / 2  # centre the model on the origin

    build_nose(spec, z)
    z -= spec["nose"]["length_m"]
    for i, tube in enumerate(spec["body"]):
        if i > 0:
            build_transition(tube, spec["body"][i - 1], z, i)
        build_tube(tube, i, z)
        z -= tube["length_m"]
    build_fins(spec, z)


def pick_engine():
    """The EEVEE enum name moved between Blender versions. Ask, do not guess."""
    available = bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items.keys()
    for name in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "BLENDER_WORKBENCH"):
        if name in available:
            return name
    return available[0]


def scene_bounds():
    """World-space min/max over every mesh in the scene."""
    lo = [1e9, 1e9, 1e9]
    hi = [-1e9, -1e9, -1e9]
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        for corner in obj.bound_box:
            world = obj.matrix_world @ mathutils.Vector(corner)
            for i in range(3):
                lo[i] = min(lo[i], world[i])
                hi[i] = max(hi[i], world[i])
    return mathutils.Vector(lo), mathutils.Vector(hi)


def setup_render(resolution):
    scene = bpy.context.scene
    scene.render.engine = pick_engine()
    scene.render.resolution_x, scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = True

    lo, hi = scene_bounds()
    centre = (lo + hi) / 2
    size = max((hi - lo).length, 1e-3)
    radius = size / 2

    target = bpy.data.objects.new("target", None)
    bpy.context.collection.objects.link(target)
    target.location = centre

    bpy.ops.object.camera_add()
    camera = bpy.context.active_object
    camera.data.lens = 50
    scene.camera = camera

    # Fit the bounding sphere to whichever field of view is tighter. A rocket
    # is long and thin, so on a 16:9 frame that is always the vertical one.
    sensor = camera.data.sensor_width
    aspect = resolution[1] / resolution[0]
    fov_x = 2 * math.atan(sensor / 2 / camera.data.lens)
    fov_y = 2 * math.atan(sensor * aspect / 2 / camera.data.lens)
    distance = radius / math.sin(min(fov_x, fov_y) / 2) * 1.12

    # Three-quarter view, slightly above the centre.
    direction = mathutils.Vector((0.62, -0.72, 0.31)).normalized()
    camera.location = centre + direction * distance
    track = camera.constraints.new("TRACK_TO")
    track.target = target
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"

    key = bpy.data.lights.new("key", "AREA")
    key.energy = size * size * 220
    key.size = size
    key_obj = bpy.data.objects.new("key", key)
    key_obj.location = centre + mathutils.Vector((size, -size, size * 1.5))
    bpy.context.collection.objects.link(key_obj)
    key_obj.constraints.new("TRACK_TO").target = target

    world = bpy.data.worlds.new("world")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.25
    scene.world = world

    shell = bpy.data.materials.new("shell")
    shell.use_nodes = True
    bsdf = shell.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.78, 0.80, 0.84, 1)
    bsdf.inputs["Roughness"].default_value = 0.25
    bsdf.inputs["Metallic"].default_value = 0.15
    for obj in scene.objects:
        if obj.type == "MESH" and not obj.data.materials:
            obj.data.materials.append(shell)


def main():
    with open(sys.argv[sys.argv.index("--") + 1]) as fh:
        payload = json.load(fh)
    spec = payload["spec"]

    build_rocket(spec)

    if payload.get("out"):
        bpy.ops.export_scene.gltf(
            filepath=payload["out"],
            export_format="GLB",
            export_extras=True,  # carries rocinante_part through to the viewer
            use_selection=False,
        )
        print(f"[rocinante] wrote {payload['out']}")

    if payload.get("render"):
        setup_render(payload["render"]["resolution"])
        bpy.context.scene.render.filepath = payload["render"]["path"]
        bpy.ops.render.render(write_still=True)
        print(f"[rocinante] rendered {payload['render']['path']}")


if __name__ == "__main__":
    main()
