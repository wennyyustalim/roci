"""Build a wholly parametric, original utilitarian gunship inside Blender.

Every visual island for a review part is joined into that part's mesh.  The
semantic names are therefore stable even as a ShipSpec refit changes geometry.
"""

import json
import math
import sys
from itertools import pairwise

import bpy

PART = "rocinante_part"
FACETS = 8
MATERIAL_KEYS = ("hull", "panel", "dark", "drive", "drive_hot")


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def tag(obj, part_name):
    obj[PART] = part_name
    obj.name = part_name
    return obj


class MeshBuilder:
    """Small mesh assembler with material indexes stable for glTF."""

    def __init__(self):
        self.verts, self.faces, self.materials = [], [], []

    def vertex(self, point):
        self.verts.append(tuple(point))
        return len(self.verts) - 1

    def face(self, verts, material="hull"):
        self.faces.append(tuple(verts))
        self.materials.append(MATERIAL_KEYS.index(material))


def mesh_from(name, builder):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(builder.verts, [], builder.faces)
    mesh.validate()
    for polygon, material_index in zip(mesh.polygons, builder.materials):
        polygon.material_index = material_index
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def _add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def _scale(a, amount):
    return tuple(x * amount for x in a)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(vector):
    length = math.sqrt(sum(value * value for value in vector)) or 1.0
    return _scale(vector, 1 / length)


def _ring(builder, z, rx, ry, facets=FACETS):
    return [builder.vertex((rx * math.cos(2 * math.pi * i / facets + math.pi / facets),
                            ry * math.sin(2 * math.pi * i / facets + math.pi / facets), z))
            for i in range(facets)]


def add_faceted_shell(builder, sections, material="hull", cap_material=None, panel_faces=()):
    """Eight-sided longitudinal shell; flats deliberately replace rocket curves."""
    rings = [_ring(builder, z, rx, ry) for z, rx, ry in sections]
    for station, (lower, upper) in enumerate(pairwise(rings)):
        for i in range(FACETS):
            next_i = (i + 1) % FACETS
            face_material = "panel" if (station, i) in panel_faces else material
            builder.face((lower[i], lower[next_i], upper[next_i], upper[i]), face_material)
    cap = cap_material or material
    builder.face(tuple(reversed(rings[0])), cap)
    builder.face(tuple(rings[-1]), cap)


def _basis_for(axis):
    axis = _unit(axis)
    reference = (0, 0, 1) if abs(axis[2]) < 0.9 else (1, 0, 0)
    u = _unit(_cross(reference, axis))
    return axis, u, _cross(axis, u)


def _disc(builder, center, normal, radius, material, facets=12):
    _, u, v = _basis_for(normal)
    center_index = builder.vertex(center)
    rim = []
    for i in range(facets):
        angle = 2 * math.pi * i / facets
        rim.append(builder.vertex(_add(center, _scale(_add(_scale(u, math.cos(angle)), _scale(v, math.sin(angle))), radius))))
    for i in range(facets):
        builder.face((center_index, rim[i], rim[(i + 1) % facets]), material)


def _box(builder, center, size, material="panel", basis=None):
    """A cuboid in a local frame. Useful for actual plates, not decorations."""
    if basis is None:
        basis = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
    axes = tuple(_unit(axis) for axis in basis)
    half = tuple(value / 2 for value in size)
    corners = []
    for sx, sy, sz in ((-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
                       (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)):
        offset = _add(_add(_scale(axes[0], sx * half[0]), _scale(axes[1], sy * half[1])),
                      _scale(axes[2], sz * half[2]))
        corners.append(builder.vertex(_add(center, offset)))
    for indexes in ((3, 2, 1, 0), (5, 6, 7, 4), (1, 5, 4, 0),
                    (2, 6, 5, 1), (3, 7, 6, 2), (0, 4, 7, 3)):
        builder.face(tuple(corners[i] for i in indexes), material)


def _cylinder(builder, start, end, radius, material="panel", cap_material=None, facets=10):
    _, u, v = _basis_for(_sub(end, start))
    first, last = [], []
    for i in range(facets):
        angle = 2 * math.pi * i / facets
        radial = _scale(_add(_scale(u, math.cos(angle)), _scale(v, math.sin(angle))), radius)
        first.append(builder.vertex(_add(start, radial)))
        last.append(builder.vertex(_add(end, radial)))
    for i in range(facets):
        next_i = (i + 1) % facets
        builder.face((first[i], first[next_i], last[next_i], last[i]), material)
    cap = cap_material or material
    builder.face(tuple(reversed(first)), cap)
    builder.face(tuple(last), cap)


def _tube(builder, start, end, outer_radius, inner_radius, material="panel", bore="dark", facets=12):
    """An annular launch tube with a dark, recessed aperture at its nose."""
    axis, u, v = _basis_for(_sub(end, start))
    rings = [[], [], [], []]
    for i in range(facets):
        angle = 2 * math.pi * i / facets
        direction = _add(_scale(u, math.cos(angle)), _scale(v, math.sin(angle)))
        for ring, origin, radius in ((rings[0], start, outer_radius), (rings[1], end, outer_radius),
                                     (rings[2], start, inner_radius), (rings[3], end, inner_radius)):
            ring.append(builder.vertex(_add(origin, _scale(direction, radius))))
    for i in range(facets):
        next_i = (i + 1) % facets
        builder.face((rings[0][i], rings[0][next_i], rings[1][next_i], rings[1][i]), material)
        builder.face((rings[2][next_i], rings[2][i], rings[3][i], rings[3][next_i]), bore)
        builder.face((rings[1][i], rings[1][next_i], rings[3][next_i], rings[3][i]), material)
        builder.face((rings[2][next_i], rings[2][i], rings[0][i], rings[0][next_i]), material)
    _disc(builder, _sub(end, _scale(axis, 0.06)), axis, inner_radius * 0.94, bore, facets)


def hull_profile(hull, steps=None):
    """Faceted profile: broad working hull, steep shoulders, chamfered prow."""
    length, radius, taper = hull["length_m"], hull["beam_m"] / 2, hull["taper"]
    return [
        (0.00 * length, radius * 0.72),
        (0.08 * length, radius * 0.92),
        (0.28 * length, radius),
        (0.55 * length, radius * 0.94),
        (0.72 * length, radius * (0.66 + 0.34 * taper)),
        (0.86 * length, radius * taper),
        (0.96 * length, radius * taper * 0.42),
        (1.00 * length, max(radius * taper * 0.10, 0.10)),
    ]


def hull_sections(hull):
    """Y is thinner than beam: a pressure hull with a visible belly and spine."""
    return [(z, radius, radius * 0.74) for z, radius in hull_profile(hull)]


def hull_radius_at(hull, z):
    """Local elliptical radius for flush PDCs, tubes, and interior decks."""
    profile = hull_profile(hull)
    z = min(max(z, profile[0][0]), profile[-1][0])
    for (first_z, first_r), (last_z, last_r) in pairwise(profile):
        if z <= last_z:
            fraction = (z - first_z) / (last_z - first_z)
            radius = first_r + (last_r - first_r) * fraction
            return radius, radius * 0.74
    return profile[-1][1], profile[-1][1] * 0.74


def faceted_surface_distance(rx, ry, radial):
    """Distance to the actual octagonal shell along a unit XY ray.

    ``hull_radius_at`` describes the enclosing ellipse.  Mounts must use this
    apothem intersection instead, otherwise cardinal placements visibly hover
    above an octagonal face.
    """
    scaled_direction = (radial[0] / rx, radial[1] / ry)
    face_normals = [(math.cos(math.pi / 4 + i * math.pi / 4),
                     math.sin(math.pi / 4 + i * math.pi / 4)) for i in range(FACETS)]
    denominator = max(nx * scaled_direction[0] + ny * scaled_direction[1]
                      for nx, ny in face_normals)
    return math.cos(math.pi / FACETS) / denominator


def faceted_y_at_x(rx, ry, x):
    """Positive Y face of the octagonal shell at a chosen X tube column."""
    normalized_x = x / rx
    limits = []
    for index in range(FACETS):
        nx = math.cos(math.pi / 4 + index * math.pi / 4)
        ny = math.sin(math.pi / 4 + index * math.pi / 4)
        if ny > 1e-9:
            limits.append((math.cos(math.pi / FACETS) - nx * normalized_x) / ny)
    return ry * min(limits)


def build_hull(spec):
    hull = spec["hull"]
    builder = MeshBuilder()
    # Pale panel facets are actual pressure-hull faces, not floating plates.
    add_faceted_shell(builder, hull_sections(hull), panel_faces={(1, 0), (1, 1), (2, 0), (2, 1),
                                                                  (4, 0), (4, 1), (5, 0)})
    return [tag(mesh_from("hull_body", builder), "hull_body")]


def build_drive(spec):
    hull, drive = spec["hull"], spec["drive"]
    _, hull_ry = hull_radius_at(hull, 0)
    neck_radius = min(drive["cone_radius_m"] * 0.44, hull_ry * 0.82)
    cone_builder = MeshBuilder()
    add_faceted_shell(cone_builder, sorted([
        (0.02, neck_radius * 1.10, neck_radius * 0.82),
        (-drive["cone_length_m"] * 0.30, drive["cone_radius_m"] * 0.72, drive["cone_radius_m"] * 0.54),
        (-drive["cone_length_m"] * 0.86, drive["cone_radius_m"] * 0.98, drive["cone_radius_m"] * 0.74),
    ], key=lambda section: section[0]), "panel")
    for side in (-1, 1):
        _box(cone_builder, (side * neck_radius * 0.90, 0, -drive["cone_length_m"] * 0.30),
             (0.20, neck_radius * 1.05, drive["cone_length_m"] * 0.42), "hull")
    cone = tag(mesh_from("drive_cone", cone_builder), "drive_cone")
    bell_builder = MeshBuilder()
    bell_z, bell_length = -drive["cone_length_m"] * 0.88, max(1.2, drive["cone_length_m"] * 0.18)
    outer = drive["cone_radius_m"] * 1.08
    _tube(bell_builder, (0, 0, bell_z), (0, 0, bell_z - bell_length), outer, outer * 0.70, "drive", "dark")
    _disc(bell_builder, (0, 0, bell_z - bell_length - 0.015), (0, 0, -1), outer * 0.65, "drive_hot")
    _tube(bell_builder, (0, 0, bell_z + 0.18), (0, 0, bell_z - bell_length * 0.18), outer * 1.03,
          outer * 0.91, "panel", "dark")
    bell = tag(mesh_from("drive_bell", bell_builder), "drive_bell")
    return [cone, bell]


def build_pdcs(spec):
    """PDC bases intersect their hull surface, so no turrets float."""
    hull, weapons = spec["hull"], spec["weapons"]
    out, count = [], weapons["pdc_mounts"]
    for index in range(count):
        band = index % 2
        z = hull["length_m"] * (0.30 if band == 0 else 0.57)
        angle = 2 * math.pi * (index // 2 + 0.25 + 0.5 * band) / max(1, math.ceil(count / 2))
        radial, tangent = (math.cos(angle), math.sin(angle), 0), (-math.sin(angle), math.cos(angle), 0)
        rx, ry = hull_radius_at(hull, z)
        surface = faceted_surface_distance(rx, ry, radial)
        basis, builder = (tangent, radial, (0, 0, -1)), MeshBuilder()
        mount = (radial[0] * (surface + 0.18), radial[1] * (surface + 0.18), z)
        pedestal_base = (radial[0] * (surface + 0.43), radial[1] * (surface + 0.43), z)
        pedestal_top = (radial[0] * (surface + 0.96), radial[1] * (surface + 0.96), z)
        _box(builder, mount, (1.70, 0.42, 1.15), "panel", basis)
        _cylinder(builder, pedestal_base, pedestal_top, 0.46, "hull", "panel", 8)
        turret = (radial[0] * (surface + 1.03), radial[1] * (surface + 1.03), z)
        _box(builder, turret, (1.20, 0.58, 0.68), "dark", basis)
        aim = _unit(_add(radial, (0, 0, 0.24)))
        for offset in (-0.26, 0.26):
            start = _add(turret, _add(_scale(tangent, offset), _scale(aim, 0.22)))
            _cylinder(builder, start, _add(start, _scale(aim, 1.45)), 0.13, "dark", "panel", 8)
        out.append(tag(mesh_from(f"pdc_{index + 1:02d}", builder), f"pdc_{index + 1:02d}"))
    return out


def build_tubes(spec):
    """Forward tubes on +Y, clear from the viewer's +Y quarter framing."""
    hull, weapons = spec["hull"], spec["weapons"]
    count, out = weapons["torpedo_tubes"], []
    columns = min(3, max(1, count))
    for index in range(count):
        row, column = divmod(index, columns)
        z = hull["length_m"] * (0.74 - row * 0.055)
        rx, ry = hull_radius_at(hull, z)
        x = (column - (columns - 1) / 2) * min(2.35, rx * 0.34)
        y_skin = faceted_y_at_x(rx, ry, x)
        y = y_skin + 0.16
        builder = MeshBuilder()
        _tube(builder, (x, y, z - 1.62), (x, y, z + 1.62), 0.68, 0.42, "panel", "dark")
        _box(builder, (x, y - 0.10, z), (1.58, 0.26, 3.42), "hull")
        out.append(tag(mesh_from(f"tube_{index + 1:02d}", builder), f"tube_{index + 1:02d}"))
    return out


def build_decks(spec):
    """Deck plates remain 30% clear of the local hull; they cannot protrude."""
    hull, out = spec["hull"], []
    stack, z, available = sum(deck["height_m"] for deck in spec["decks"]), hull["length_m"] * 0.20, hull["length_m"] * 0.48
    for index, deck in enumerate(spec["decks"]):
        rx, ry = hull_radius_at(hull, z)
        builder = MeshBuilder()
        add_faceted_shell(builder, [(z - 0.055, rx * 0.70, ry * 0.70), (z + 0.055, rx * 0.70, ry * 0.70)],
                          "panel" if deck["kind"] != "galley" else "hull")
        name = f"deck_{index + 1:02d}_{deck['kind']}"
        out.append(tag(mesh_from(name, builder), name))
        z += deck["height_m"] * available / stack if stack else available
    return out


def apply_materials(objects):
    """Graphite, panel grey, recess black, ceramic drive, contained blue core."""
    def make(name, color, metallic, roughness, emission=None):
        value = bpy.data.materials.new(name)
        value.use_nodes = True
        node = value.node_tree.nodes["Principled BSDF"]
        node.inputs["Base Color"].default_value = color
        node.inputs["Metallic"].default_value, node.inputs["Roughness"].default_value = metallic, roughness
        if emission and "Emission Color" in node.inputs:
            node.inputs["Emission Color"].default_value, node.inputs["Emission Strength"].default_value = emission
        return value
    materials = (
        make("hull_graphite", (0.16, 0.18, 0.21, 1), 0.76, 0.42),
        make("armor_panel", (0.32, 0.35, 0.39, 1), 0.68, 0.46),
        make("recess_black", (0.025, 0.032, 0.045, 1), 0.42, 0.32),
        make("drive_ceramic", (0.28, 0.17, 0.09, 1), 0.62, 0.36),
        make("drive_core", (0.10, 0.18, 0.34, 1), 0.22, 0.24, ((0.20, 0.48, 1.0, 1), 1.5)),
    )
    for obj in objects:
        for material in materials:
            obj.data.materials.append(material)


def frame_camera(objects):
    xs, ys, zs = [], [], []
    for obj in objects:
        for corner in obj.bound_box:
            world = obj.matrix_world @ __import__("mathutils").Vector(corner)
            xs.append(world.x); ys.append(world.y); zs.append(world.z)
    cx, cy, cz = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2
    span = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)) or 1.0
    cam = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
    bpy.context.collection.objects.link(cam)
    cam.location, cam.data.lens = (cx + span * 1.45, cy + span * 2.00, cz + span * 0.76), 40
    bpy.context.scene.camera = cam
    target = bpy.data.objects.new("focus", None)
    bpy.context.collection.objects.link(target)
    target.location = (cx, cy, cz + span * 0.04)
    track = cam.constraints.new("TRACK_TO")
    track.target, track.track_axis, track.up_axis = target, "TRACK_NEGATIVE_Z", "UP_Y"
    return span, (cx, cy, cz)


def add_lights(span, center):
    from mathutils import Vector

    def point_at(obj):
        obj.rotation_euler = (Vector(center) - obj.location).to_track_quat("-Z", "Y").to_euler()

    key = bpy.data.lights.new("key", type="AREA")
    key.energy, key.shape, key.size = span * span * 48, "DISK", span * 0.8
    key_obj = bpy.data.objects.new("key", key)
    bpy.context.collection.objects.link(key_obj)
    key_obj.location = _add(center, (span * 0.85, span * 1.20, span * 0.80))
    point_at(key_obj)
    rim = bpy.data.lights.new("rim", type="AREA")
    rim.energy, rim.shape, rim.size = span * span * 32, "RECTANGLE", span * 0.6
    rim_obj = bpy.data.objects.new("rim", rim)
    bpy.context.collection.objects.link(rim_obj)
    rim_obj.location = _add(center, (-span * 1.0, -span * 0.8, span * 0.35))
    point_at(rim_obj)


def main():
    with open(sys.argv[sys.argv.index("--") + 1]) as fh:
        payload = json.load(fh)
    spec = payload["spec"]
    clear_scene()
    objects = build_hull(spec) + build_drive(spec) + build_pdcs(spec) + build_tubes(spec) + build_decks(spec)
    apply_materials(objects)
    # Bound boxes and camera framing must see the evaluated, materialized mesh.
    bpy.context.view_layer.update()
    span, center = frame_camera(objects)
    add_lights(span, center)
    if payload.get("out"):
        bpy.ops.export_scene.gltf(filepath=payload["out"], export_format="GLB", export_extras=True, export_apply=True)
        print(f"wrote {payload['out']} ({len(objects)} parts)")
    if render := payload.get("render"):
        scene = bpy.context.scene
        scene.render.engine = "BLENDER_EEVEE"
        scene.render.resolution_x, scene.render.resolution_y = render["resolution"]
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format, scene.render.filepath = "PNG", render["path"]
        scene.render.image_settings.color_mode = "RGB"
        scene.render.film_transparent = False
        if scene.world is None:
            scene.world = bpy.data.worlds.new("world")
        scene.world.color = (0.012, 0.016, 0.025)
        scene.world.use_nodes = True
        background = scene.world.node_tree.nodes.get("Background")
        background.inputs["Color"].default_value = (0.012, 0.016, 0.025, 1)
        background.inputs["Strength"].default_value = 0.22
        # EEVEE can compile its material graph lazily on the first headless
        # draw. Warm it before writing the demo artifact, avoiding blank frames.
        bpy.ops.render.render()
        bpy.ops.render.render(write_still=True)
        print(f"rendered {render['path']}")


if __name__ == "__main__":
    main()
