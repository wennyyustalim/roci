"""Physical-size loaded rounds; no detached or enlarged presentation model."""
import bpy
from build_rocket import build_fins, build_nose, build_tube
from mathutils import Vector


def _material(name, color, metallic=0.5, roughness=0.3):
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.diffuse_color = (*color, 1)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return material


def _detail(obj, ident, origin, material):
    obj.location += origin
    obj["rocinante_part"] = ident
    obj["assembly_kind"] = "torpedo"
    obj["torpedo_id"] = ident
    obj.name = f"{ident}_{obj.name}"
    obj.data.materials.append(material)
    return obj


def _cylinder(name, radius, depth, z, material, origin, ident, vertices=32):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=(0, 0, z))
    return _detail(bpy.context.active_object, ident, origin, material)


def _torpedo_hardware(rocket, origin, ident):
    """Add readable ordnance hardware around the otherwise aerodynamic core."""
    body = rocket["body"]
    radius = body[-1]["outer_radius_m"]
    nose_len = rocket["nose"]["length_m"]
    total_body = sum(section["length_m"] for section in body)
    body_center = -nose_len / 2
    aft = body_center - total_body / 2
    dark = _material("torpedo_seams", (0.025, 0.04, 0.05), .5, .35)
    steel = _material("torpedo_hardware", (0.48, 0.55, 0.57), .85, .2)
    amber = _material("torpedo_ident", (0.95, 0.34, 0.05), .35, .32)
    # Nose lock and seeker collar make the front unmistakable at a distance.
    _cylinder("nose_lock", radius * 1.035, radius * .10, body_center + total_body / 2 - radius * .06, steel, origin, ident)
    _cylinder("ident_band", radius * 1.04, radius * .13, body_center + total_body / 2 - radius * .22, amber, origin, ident)
    _cylinder("band_seam", radius * 1.045, radius * .025, body_center + total_body / 2 - radius * .31, dark, origin, ident)
    # Section collars and captive fasteners across the modular pressure hull.
    cursor = body_center + total_body / 2
    for index, section in enumerate(body):
        length = section["length_m"]
        cursor -= length
        _cylinder(f"collar_{index}", radius * 1.025, min(radius * .055, length * .08), cursor, dark if index % 2 else steel, origin, ident)
        if length > radius * 1.5:
            for side in range(4):
                angle = side * 3.14159265 / 2
                x, y = radius * 1.018 * __import__("math").sin(angle), radius * 1.018 * __import__("math").cos(angle)
                bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, cursor + length * .47))
                screw = bpy.context.active_object
                screw.name = f"service_lock_{index}_{side}"
                screw.dimensions = (radius * .12, radius * .05, radius * .045)
                screw.rotation_euler[2] = angle
                bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
                _detail(screw, ident, origin, steel)
    # A dark recessed exhaust and a ring of tail flutes sell the propulsion end.
    _cylinder("nozzle_rim", radius * .70, radius * .12, aft - radius * .05, steel, origin, ident)
    _cylinder("nozzle_recess", radius * .42, radius * .13, aft - radius * .12, dark, origin, ident)
    for index in range(8):
        angle = index * 3.14159265 / 4
        x, y = radius * .78 * __import__("math").sin(angle), radius * .78 * __import__("math").cos(angle)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, aft + radius * .01))
        flute = bpy.context.active_object
        flute.name = f"tail_flute_{index}"
        flute.dimensions = (radius * .08, radius * .18, radius * .035)
        flute.rotation_euler[2] = angle
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        _detail(flute, ident, origin, steel)


def build_loaded_torpedoes(spec, tubes, overrides=None):
    overrides = overrides or {}
    made = []
    bpy.context.view_layer.update()
    material = bpy.data.materials.get("loaded_torpedo") or bpy.data.materials.new("loaded_torpedo")
    material.diffuse_color = (1.0, .58, .12, 1)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (1.0, .58, .12, 1)
    bsdf.inputs["Metallic"].default_value = .4
    bsdf.inputs["Roughness"].default_value = .35
    for tube in tubes:
        ident = tube["rocinante_part"].replace("tube_", "torpedo_")
        rocket = overrides.get(ident, spec["torpedo"])
        points = [tube.matrix_world @ Vector(c) for c in tube.bound_box]
        lo = Vector(tuple(min(p[i] for p in points) for i in range(3)))
        hi = Vector(tuple(max(p[i] for p in points) for i in range(3)))
        center = (lo + hi) / 2
        side = 1 if center.y > 0 else -1
        clearance = rocket["body"][-1]["outer_radius_m"] + rocket["fins"]["height_m"] + .04
        length = rocket["nose"]["length_m"] + sum(t["length_m"] for t in rocket["body"])
        origin = Vector((center.x, hi.y + clearance if side > 0 else lo.y - clearance, center.z - length/2))
        z = length
        parts = [build_nose(rocket, z)]
        z -= rocket["nose"]["length_m"]
        for i, body in enumerate(rocket["body"]):
            parts.append(build_tube(body, i, z))
            z -= body["length_m"]
        parts += build_fins(rocket, 0)
        for part in parts:
            part.location += origin
            part["rocinante_part"] = ident
            part["assembly_kind"] = "torpedo"
            part["torpedo_id"] = ident
            part.name = f"{ident}_{part.name}"
            part.data.materials.clear()
            part.data.materials.append(material)
        made.extend(parts)
        _torpedo_hardware(rocket, origin, ident)
    return made
