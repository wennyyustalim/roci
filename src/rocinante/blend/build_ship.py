"""Runs INSIDE Blender. Not importable from the host -- `bpy` only exists there.

    blender --background --factory-startup --python build_ship.py -- payload.json

payload.json is {"spec": <ShipSpec dump>, "out": "x.glb"|null,
                 "render": {"path": ..., "resolution": [w, h]}|null}

THE RULE THIS FILE EXISTS TO ENFORCE: the hull is generated, never modelled.
A hand-sculpted Rocinante cannot regenerate when the spec changes, and
regenerating is the entire demo. Buy "pretty" with lighting and materials
here, never with geometry a human placed by hand.

Every mesh carries the custom property `rocinante_part`, named `hull_*`,
`drive_*`, `pdc_*`, `tube_*` or `deck_*`. Kord's glTF viewer reads node names
into its part tree, and the diff lines the two sides up part by part -- so the
naming convention is load-bearing, not cosmetic. Agree it before you edit.
"""

import json
import math
import sys

import bpy

PART = "rocinante_part"

# +Z is the thrust axis, nose up. Deck floors are normal to it, which is what
# makes "the ship is a building standing on its drive" read correctly.


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def tag(obj, part_name):
    obj[PART] = part_name
    obj.name = part_name
    return obj


def mesh_from(name, verts, faces):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.validate()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def lathe(name, profile, segments=48, z_offset=0.0):
    """Revolve a list of (z, radius) around the Z axis."""
    verts, faces = [], []
    for z, r in profile:
        ring = len(verts)
        r = max(r, 1e-4)
        for s in range(segments):
            a = 2 * math.pi * s / segments
            verts.append((r * math.cos(a), r * math.sin(a), z + z_offset))
        if ring:
            prev = ring - segments
            for s in range(segments):
                n = (s + 1) % segments
                faces.append((prev + s, prev + n, ring + n, ring + s))
    return mesh_from(name, verts, faces)


def hull_profile(hull, steps=24):
    """Radius along the body. A rounded nose easing into the tapered barrel."""
    length = hull["length_m"]
    r_max = hull["beam_m"] / 2
    r_nose = r_max * hull["taper"]
    nose_len = length * 0.28
    pts = []
    for i in range(steps + 1):  # nose: quarter-ellipse from r_nose to the tip
        f = i / steps
        pts.append((length - nose_len + nose_len * f, r_nose * math.sqrt(max(0.0, 1 - f**2))))
    for i in range(1, steps + 1):  # barrel: nose radius flaring to the beam
        f = i / steps
        pts.append((length - nose_len - (length - nose_len) * f, r_nose + (r_max - r_nose) * f**0.7))
    return sorted(pts)


def build_hull(spec):
    hull = spec["hull"]
    body = tag(lathe("hull_body", hull_profile(hull)), "hull_body")
    return [body]


def build_drive(spec):
    """The cone aft of the hull. Lengthening it is the demo's canonical refit."""
    drive = spec["drive"]
    r_throat = drive["cone_radius_m"] * 0.30
    profile = []
    steps = 16
    for i in range(steps + 1):
        f = i / steps
        profile.append((-drive["cone_length_m"] * f, r_throat + (drive["cone_radius_m"] - r_throat) * f**1.4))
    cone = tag(lathe("drive_cone", sorted(profile)), "drive_cone")

    bell = tag(lathe("drive_bell", [(-drive["cone_length_m"], drive["cone_radius_m"]),
                                    (-drive["cone_length_m"] - 0.8, drive["cone_radius_m"] * 1.08)]),
               "drive_bell")
    return [cone, bell]


def build_pdcs(spec):
    """Point-defence blisters, ringed around the hull at two stations."""
    hull, weapons = spec["hull"], spec["weapons"]
    r = hull["beam_m"] / 2
    out = []
    count = weapons["pdc_mounts"]
    for i in range(count):
        band = i % 2
        z = hull["length_m"] * (0.62 if band else 0.34)
        angle = 2 * math.pi * (i // 2 + 0.5 * band) / max(1, math.ceil(count / 2))
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.9, segments=16, ring_count=8)
        obj = bpy.context.active_object
        obj.location = (r * 0.92 * math.cos(angle), r * 0.92 * math.sin(angle), z)
        obj.scale = (1.0, 1.0, 0.6)
        out.append(tag(obj, f"pdc_{i + 1:02d}"))
    return out


def build_tubes(spec):
    """Torpedo tube ports, forward, in two rows. Trading these is a real refit."""
    hull, weapons = spec["hull"], spec["weapons"]
    r = hull["beam_m"] / 2 * spec["hull"]["taper"]
    out = []
    for i in range(weapons["torpedo_tubes"]):
        row, col = divmod(i, 2)
        bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.55, depth=2.4)
        obj = bpy.context.active_object
        obj.rotation_euler = (math.pi / 2, 0, 0)
        obj.location = (
            (col - 0.5) * 2.2,
            r * 0.75,
            hull["length_m"] * (0.80 - row * 0.07),
        )
        out.append(tag(obj, f"tube_{i + 1:02d}"))
    return out


def build_decks(spec):
    """One floor plate per deck. The galley is the only one worth detailing."""
    hull = spec["hull"]
    out = []
    stack = sum(d["height_m"] for d in spec["decks"]) or hull["length_m"] * 0.6
    base = hull["length_m"] * 0.18
    z = base
    for i, deck in enumerate(spec["decks"]):
        f = 1 - (z / hull["length_m"]) * 0.45
        bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=hull["beam_m"] / 2 * 0.82 * f, depth=0.12)
        obj = bpy.context.active_object
        obj.location = (0, 0, z)
        out.append(tag(obj, f"deck_{i + 1:02d}_{deck['kind']}"))
        z += deck["height_m"] * (hull["length_m"] * 0.6 / stack if stack else 1)
    return out


def apply_materials(objects):
    """Two materials. All of the ship's looks come from here and the lights."""
    hull_mat = bpy.data.materials.new("hull")
    hull_mat.use_nodes = True
    bsdf = hull_mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.32, 0.33, 0.35, 1.0)
    bsdf.inputs["Metallic"].default_value = 0.85
    bsdf.inputs["Roughness"].default_value = 0.42

    drive_mat = bpy.data.materials.new("drive")
    drive_mat.use_nodes = True
    dnode = drive_mat.node_tree.nodes["Principled BSDF"]
    dnode.inputs["Base Color"].default_value = (0.55, 0.30, 0.12, 1.0)
    dnode.inputs["Roughness"].default_value = 0.30
    if "Emission Color" in dnode.inputs:
        dnode.inputs["Emission Color"].default_value = (1.0, 0.45, 0.15, 1.0)
        dnode.inputs["Emission Strength"].default_value = 2.5

    for obj in objects:
        mat = drive_mat if obj[PART].startswith("drive_") else hull_mat
        obj.data.materials.append(mat)


def frame_camera(objects):
    """Auto-frame whatever got built, so a refit never walks out of shot."""
    xs, ys, zs = [], [], []
    for obj in objects:
        for corner in obj.bound_box:
            world = obj.matrix_world @ __import__("mathutils").Vector(corner)
            xs.append(world.x); ys.append(world.y); zs.append(world.z)
    cx, cy, cz = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2
    span = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)) or 1.0

    cam_data = bpy.data.cameras.new("camera")
    cam = bpy.data.objects.new("camera", cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = (cx + span * 1.2, cy - span * 1.6, cz + span * 0.55)
    bpy.context.scene.camera = cam

    target = bpy.data.objects.new("focus", None)
    bpy.context.collection.objects.link(target)
    target.location = (cx, cy, cz)
    track = cam.constraints.new("TRACK_TO")
    track.target = target
    return span


def add_lights(span):
    key = bpy.data.lights.new("key", type="AREA")
    key.energy = span * span * 40
    key.size = span
    obj = bpy.data.objects.new("key", key)
    bpy.context.collection.objects.link(obj)
    obj.location = (span * 1.4, -span * 1.2, span * 1.5)
    obj.rotation_euler = (0.9, 0.0, 0.7)

    rim = bpy.data.lights.new("rim", type="AREA")
    rim.energy = span * span * 18
    rim.size = span * 0.6
    robj = bpy.data.objects.new("rim", rim)
    bpy.context.collection.objects.link(robj)
    robj.location = (-span * 1.5, span * 1.0, span * 0.4)
    robj.rotation_euler = (1.3, 0.0, -2.2)


def main():
    with open(sys.argv[sys.argv.index("--") + 1]) as fh:
        payload = json.load(fh)
    spec = payload["spec"]

    clear_scene()
    objects = (
        build_hull(spec)
        + build_drive(spec)
        + build_pdcs(spec)
        + build_tubes(spec)
        + build_decks(spec)
    )
    apply_materials(objects)
    span = frame_camera(objects)
    add_lights(span)

    if payload.get("out"):
        bpy.ops.export_scene.gltf(
            filepath=payload["out"],
            export_format="GLB",
            export_extras=True,   # carries rocinante_part into the glTF
            export_apply=True,
        )
        print(f"wrote {payload['out']} ({len(objects)} parts)")

    render = payload.get("render")
    if render:
        scene = bpy.context.scene
        scene.render.engine = "BLENDER_EEVEE_NEXT"
        scene.render.resolution_x, scene.render.resolution_y = render["resolution"]
        scene.render.filepath = render["path"]
        scene.render.film_transparent = False
        bpy.ops.render.render(write_still=True)
        print(f"rendered {render['path']}")


main()
