"""Physical-size loaded rounds; no detached or enlarged presentation model."""
import bpy
from mathutils import Vector
from build_rocket import build_fins, build_nose, build_tube


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
    return made
