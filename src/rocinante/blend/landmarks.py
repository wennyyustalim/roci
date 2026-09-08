"""Browser landmark geometry, baked by scripts/export-landmarks.mjs."""
import gzip
import json
from pathlib import Path

import bpy
from mathutils import Matrix


def build_landmark(ident):
    existing = [o for o in bpy.context.scene.objects if o.get("landmark_id") == ident]
    if existing:
        return existing
    with gzip.open(Path(__file__).with_name("landmarks.json.gz"), "rt") as file:
        data = json.load(file)
    meshes, materials, objects = {}, {}, []
    # Three.js Y-up to Blender Z-up, matching the ship's glTF export.
    axes = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
    for item in data["objects"]:
        if item["id"] != ident:
            continue
        style = item["material"]
        # The web Ring field is a screen shader, not an opaque physical panel.
        if style["opacity"] < .1:
            continue
        key = (item["geometry"], json.dumps(style, sort_keys=True))
        if key not in meshes:
            raw = data["geometries"][item["geometry"]]
            positions, indices = raw["positions"], raw["indices"]
            mesh = bpy.data.meshes.new(f"{ident}_mesh")
            mesh.from_pydata(list(zip(*[iter(positions)] * 3)), [], list(zip(*[iter(indices)] * 3)))
            mesh.update()
            color = (*style["color"], style["opacity"])
            material_key = key[1]
            if material_key not in materials:
                material = bpy.data.materials.new(f"{ident}_surface")
                material.diffuse_color = color
                material.use_nodes = True
                shader = material.node_tree.nodes.get("Principled BSDF")
                shader.inputs["Base Color"].default_value = color
                shader.inputs["Metallic"].default_value = style["metallic"]
                shader.inputs["Roughness"].default_value = style["roughness"]
                shader.inputs["Alpha"].default_value = style["opacity"]
                if style["emission"]:
                    shader.inputs["Emission Color"].default_value = color
                    shader.inputs["Emission Strength"].default_value = 1
                materials[material_key] = material
            mesh.materials.append(materials[material_key])
            if raw["colors"]:
                colors = mesh.color_attributes.new(name="surface", type="FLOAT_COLOR", domain="POINT")
                for vertex, rgb in zip(colors.data, zip(*[iter(raw["colors"])] * 3)):
                    vertex.color = (*rgb, 1)
                material = materials[material_key]
                attribute = material.node_tree.nodes.new("ShaderNodeVertexColor")
                attribute.layer_name = "surface"
                material.node_tree.links.new(attribute.outputs["Color"], material.node_tree.nodes.get("Principled BSDF").inputs["Base Color"])
            meshes[key] = mesh
        obj = bpy.data.objects.new(f"{ident}_{len(objects):04d}", meshes[key])
        obj["landmark_id"] = ident
        bpy.context.collection.objects.link(obj)
        values = item["matrix"]
        obj.matrix_world = axes @ Matrix(tuple(tuple(values[c*4+r] for c in range(4)) for r in range(4)))
        objects.append(obj)
    return objects
