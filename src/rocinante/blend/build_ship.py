"""Build a wholly parametric, original utilitarian gunship inside Blender.

Every visual island for a review part is joined into that part's mesh.  The
semantic names are therefore stable even as a ShipSpec refit changes geometry.
"""

import json
import math
import sys
from itertools import pairwise
from pathlib import Path

import bpy

PART = "rocinante_part"
FACETS = 8
MATERIAL_KEYS = ("hull", "panel", "dark", "drive", "drive_hot", "edge", "paint", "white", "light",
                 "screen", "amber", "fabric", "skin", "skin_dark", "hair", "plant")


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


def _tube(builder, start, end, outer_radius, inner_radius, material="panel", bore="dark", facets=12, recessed=True):
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
    if recessed:
        _disc(builder, _lerp(start, end, 0.12), axis, inner_radius * 0.99, bore, facets)


def hull_profile(hull, steps=None):
    """Reference-inspired stations: engine skirt, waist, armor shoulders, bow.

    The pointed tips are separate sensor spars; the inhabited bow is blunt.
    Beam is the maximum armor envelope, with a much narrower machinery waist.
    """
    length, radius, taper = hull["length_m"], hull["beam_m"] / 2, hull["taper"]
    return [
        (0.00 * length, radius * 0.61),
        (0.025 * length, radius * 0.70),
        (0.12 * length, radius * 0.70),
        (0.145 * length, radius * 0.55),
        (0.29 * length, radius * 0.55),
        (0.32 * length, radius * 0.69),
        (0.38 * length, radius),
        (0.53 * length, radius),
        (0.60 * length, radius * 0.72),
        (0.64 * length, radius * 0.72),
        (0.79 * length, radius * (0.43 + 0.30 * taper)),
        (0.90 * length, radius * taper * 0.72),
        (0.94 * length, radius * taper * 0.63),
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


def _lerp(a, b, amount):
    return _add(a, _scale(_sub(b, a), amount))


def _plate(builder, corners, thickness, material="hull", bevel=0.08):
    """Chamfered armor tile with a dark seam and a light-catching bevel."""
    normal = _unit(_cross(_sub(corners[1], corners[0]), _sub(corners[3], corners[0])))
    center = _scale(tuple(map(sum, zip(*corners))), 0.25)
    # Clip the corners instead of drawing square, toy-like raised rectangles.
    outline = []
    for i, corner in enumerate(corners):
        outline.extend((_lerp(corner, corners[(i-1)%4], 0.055),
                        _lerp(corner, corners[(i+1)%4], 0.055)))
    lower, upper = [], []
    for corner in outline:
        lower.append(builder.vertex(corner))
        upper.append(builder.vertex(_add(_lerp(corner, center, bevel), _scale(normal, thickness))))
    builder.face(tuple(upper), material)
    builder.face(tuple(reversed(lower)), "dark")
    for i in range(8):
        j = (i + 1) % 8
        builder.face((lower[i], lower[j], upper[j], upper[i]), "edge")


def _skin_point(hull, face, z, across, lift=0.0):
    rx, ry = hull_radius_at(hull, z)
    a, b = (2 * math.pi * (face + offset) / FACETS + math.pi / FACETS for offset in (0, 1))
    point = _lerp((rx * math.cos(a), ry * math.sin(a), z),
                  (rx * math.cos(b), ry * math.sin(b), z), across)
    normal = _unit((math.cos((a + b) / 2) / rx, math.sin((a + b) / 2) / ry, 0))
    return _add(point, _scale(normal, lift))


def _skin_panel(builder, hull, face, z0, z1, u0=0.04, u1=0.96, material="hull", lift=0.04, depth=0.10):
    corners = [_skin_point(hull, face, z, u, lift) for z, u in
               ((z0, u0), (z0, u1), (z1, u1), (z1, u0))]
    _plate(builder, corners, depth, material)


def _hull_lettering(builder, hull):
    """Original ship-name and service stencils as vector geometry, no decals."""
    length = hull["length_m"]
    detail = min(length/46, hull["beam_m"]/23)
    for face in (1,5):
        for text, station, across, size in (("ROCINANTE",0.685,0.64,0.48), ("0251",0.075,0.63,0.67)):
            origin = _skin_point(hull,face,length*station,across,0.24*detail)
            along = _unit(_sub(_skin_point(hull,face,length*station+0.05,across),
                               _skin_point(hull,face,length*station-0.05,across)))
            up = (1,0,0) if face == 1 else (-1,0,0)
            normal = _unit(_cross(along,up))
            curve = bpy.data.curves.new("stencil",type="FONT")
            curve.body, curve.size, curve.extrude = text, size*detail, 0.001*detail
            curve.resolution_u = 4
            obj = bpy.data.objects.new("stencil",curve)
            bpy.context.collection.objects.link(obj)
            bpy.context.view_layer.update()
            mesh = obj.to_mesh()
            start = len(builder.verts)
            for vertex in mesh.vertices:
                builder.vertex(_add(origin,_add(_scale(along,vertex.co.x),
                                               _add(_scale(up,vertex.co.y),_scale(normal,vertex.co.z)))))
            for polygon in mesh.polygons:
                builder.face(tuple(start+index for index in polygon.vertices),"white")
            obj.to_mesh_clear()
            bpy.data.objects.remove(obj,do_unlink=True)
            bpy.data.curves.remove(curve)


def build_hull(spec):
    hull, builder = spec["hull"], MeshBuilder()
    length, radius = hull["length_m"], hull["beam_m"] / 2
    detail = min(length / 46, radius / 11.5)
    add_faceted_shell(builder, hull_sections(hull), "dark")

    # Armor follows each hull plane exactly. Seams are real gaps between tiles,
    # and the restrained red-orange paint is geometry so it survives GLB export.
    for station, ((z0, _), (z1, _)) in enumerate(pairwise(hull_profile(hull))):
        rows = max(1, round((z1 - z0) / (3.8 * detail)))
        for face in range(FACETS):
            for row in range(rows):
                low = z0 + (z1 - z0) * row / rows + 0.055 * detail
                high = z0 + (z1 - z0) * (row + 1) / rows - 0.055 * detail
                color = "panel" if (station + face * 3 + row) % 7 == 0 else "hull"
                if station in (1, 6) and face in (0, 3, 4, 7):
                    color = "panel"
                _skin_panel(builder, hull, face, low, high, material=color, depth=0.075 * detail)
                if face in (0, 3, 4, 7) and station in (6, 9, 10):
                    _skin_panel(builder, hull, face, low, high, 0.10, 0.17, "paint", 0.14 * detail, 0.01 * detail)
                # Small access covers, paired fasteners and inspection stencils.
                if station in (1, 4, 6, 9):
                    _skin_panel(builder, hull, face, low + (high-low)*0.20, low + (high-low)*0.66,
                                0.30, 0.66, "dark", 0.14 * detail, 0.025 * detail)
                    _skin_panel(builder, hull, face, low + (high-low)*0.24, low + (high-low)*0.62,
                                0.33, 0.63, "panel", 0.18 * detail, 0.025 * detail)
                    for u in (0.12, 0.88):
                        p = _skin_point(hull, face, low + (high-low)*0.15, u, 0.16 * detail)
                        normal = _unit((p[0], p[1] / 0.74**2, 0))
                        _cylinder(builder, p, _add(p, _scale(normal, 0.035*detail)), 0.055*detail, "edge", facets=6)

    # Shoulder radiators sit in dark service wells. Dense louvers, retaining
    # bars and latch blocks establish human scale on the broad armor planes.
    for face in (0, 3, 4, 7):
        _skin_panel(builder,hull,face,length*0.388,length*0.522,0.23,0.80,"dark",0.18*detail,0.04*detail)
        for row in range(16):
            low=length*(0.395+row*0.0074)
            _skin_panel(builder,hull,face,low,low+length*0.0025,0.26,0.77,"panel",0.24*detail,0.04*detail)
        for u in (0.28,0.49,0.72):
            a=_skin_point(hull,face,length*0.39,u,0.34*detail)
            b=_skin_point(hull,face,length*0.52,u,0.34*detail)
            _cylinder(builder,a,b,0.045*detail,"edge",facets=6)
        for row in range(4):
            low=length*(0.403+row*0.031)
            for u in (0.20,0.79):
                _skin_panel(builder,hull,face,low,low+length*0.008,u,u+0.045,"edge",0.29*detail,0.07*detail)

    # Narrow dorsal armor spine and offset inspection strips.
    for face in (1,5):
        for z0,z1 in ((0.325,0.375),(0.385,0.525),(0.535,0.595),(0.645,0.785),(0.795,0.895)):
            _skin_panel(builder,hull,face,length*z0,length*z1,0.055,0.19,"panel",0.18*detail,0.10*detail)
            _skin_panel(builder,hull,face,length*z0,length*z1,0.81,0.945,"panel",0.18*detail,0.10*detail)
        for row in range(6):
            low=length*(0.815+row*0.010)
            _skin_panel(builder,hull,face,low,low+length*0.004,0.35,0.65,"dark",0.15*detail,0.018*detail)

    # Deterministic fine paint wear and stencils, built into the mesh so the
    # same surface detail is visible in Blender and in the exported model.
    for face in range(FACETS):
        for index in range(32):
            low=length*(0.035+((index*0.61803398875+face*0.137)%1)*0.87)
            u=0.08+((index*0.38196601125+face*0.21)%1)*0.82
            _skin_panel(builder,hull,face,low,low+length*0.0006,u,min(u+0.023,0.96),
                        "edge",0.15*detail,0.002*detail)
        for row in range(3):
            low=length*(0.32+row*0.013)
            _skin_panel(builder,hull,face,low,low+length*0.004,0.34,0.44,"white",0.15*detail,0.002*detail)

    # Aft equipment racks: exposed conduits and heat exchangers in the waist.
    for face in range(FACETS):
        for u in (0.15, 0.27, 0.76, 0.85):
            a = _skin_point(hull, face, length*0.15, u, 0.20*detail)
            b = _skin_point(hull, face, length*0.285, u, 0.20*detail)
            _cylinder(builder, a, b, 0.085*detail, "edge", facets=8)
        for index in range(11):
            low = length * (0.17 + index*0.009)
            _skin_panel(builder, hull, face, low, low+length*0.003, 0.37, 0.65,
                        "edge", 0.19*detail, 0.025*detail)

    # Inset airlocks, ladders and equipment rails on the two broad faces.
    for face in (1, 5):
        for low, high, width in ((0.17, 0.265, (0.31, 0.69)), (0.40, 0.49, (0.35, 0.65))):
            _skin_panel(builder, hull, face, length*low, length*high, *width, "edge", 0.23*detail, 0.07*detail)
            _skin_panel(builder, hull, face, length*(low+0.008), length*(high-0.008),
                        width[0]+0.035, width[1]-0.035, "dark", 0.34*detail, 0.025*detail)
            _skin_panel(builder, hull, face, length*(low+0.015), length*(high-0.015),
                        width[0]+0.06, width[1]-0.06, "panel", 0.38*detail, 0.02*detail)
        for index in range(7):
            low = length*(0.176+index*0.012)
            _skin_panel(builder, hull, face, low, low+length*0.002, 0.73, 0.83, "edge", 0.25*detail, 0.04*detail)

    # Paired angular sensor spars give the prow its characteristic split tip.
    for side in (-1, 1):
        spar = MeshBuilder()
        add_faceted_shell(spar, [(length*0.86, radius*0.10, radius*0.14),
                                (length*0.96, radius*0.085, radius*0.11),
                                (length*1.015, radius*0.065, radius*0.045)], "panel")
        offset = (side * radius * hull["taper"] * 0.66, 0, 0)
        start = len(builder.verts)
        builder.verts.extend(_add(vertex, offset) for vertex in spar.verts)
        builder.faces.extend(tuple(index+start for index in face) for face in spar.faces)
        builder.materials.extend(spar.materials)
        for lateral, end in ((0, 1.07), (side*radius*0.055, 1.045)):
            a = (offset[0]+lateral, 0, length*0.975)
            b = (a[0], 0, length*end)
            _cylinder(builder, a, b, 0.065*detail, "edge", facets=8)
            _cylinder(builder, a, _lerp(a,b,0.35), 0.13*detail, "dark", facets=8)

    # Small recessed RCS nozzles at bow and stern, set into armor blocks.
    for z_fraction in (0.10, 0.80):
        for face in (0, 2, 4, 6):
            p = _skin_point(hull, face, length*z_fraction, 0.5, 0.20*detail)
            normal = _unit((p[0], p[1]/0.74**2, 0))
            axis, u, v = _basis_for(normal)
            _box(builder, p, (0.85*detail, 1.35*detail, 0.35*detail), "panel", (u,v,axis))
            for offset in (-0.34, 0.34):
                nozzle = _add(p, _scale(v, offset*detail))
                _tube(builder, nozzle, _add(nozzle, _scale(normal, 0.32*detail)),
                      0.22*detail, 0.15*detail, "edge", facets=12)
    _hull_lettering(builder,hull)
    # Split polygons exactly at the centre plane. Both shells keep the review
    # part ID, but have independent assembly transforms in the browser.
    halves = []
    for side, label in ((-1, "port"), (1, "starboard")):
        half = MeshBuilder()
        for face, material in zip(builder.faces, builder.materials):
            points = [builder.verts[i] for i in face]
            clipped = []
            for a, b in zip(points, points[1:] + points[:1]):
                inside_a, inside_b = side * a[0] >= 0, side * b[0] >= 0
                if inside_a:
                    clipped.append(a)
                if inside_a != inside_b:
                    clipped.append(_lerp(a, b, -a[0] / (b[0] - a[0])))
            if len(clipped) >= 3:
                half.face([half.vertex(v) for v in clipped], MATERIAL_KEYS[material])
        obj = tag(mesh_from(f"hull_{label}", half), "hull_body")
        obj.name = f"hull_{label}"
        obj["assembly_offset"] = [side * hull["beam_m"] * 0.85, 0, 0]
        obj["assembly_kind"] = "hull"
        halves.append(obj)
    return halves


def build_drive(spec):
    hull, drive = spec["hull"], spec["drive"]
    length, radius = drive["cone_length_m"], drive["cone_radius_m"]
    detail = min(length/11, radius/6.5)
    cone, bell = MeshBuilder(), MeshBuilder()
    # Visible thrust chamber behind an open triangulated load-bearing cage.
    _cylinder(cone, (0,0,0), (0,0,-length*0.57), radius*0.33, "dark", facets=32)
    for fraction in (0.04, 0.19, 0.36, 0.51):
        _tube(cone, (0,0,-length*fraction), (0,0,-length*fraction-0.16*detail),
              radius*0.38, radius*0.31, "edge", facets=32)
    rx, ry = hull_radius_at(hull, 0)
    for i in range(8):
        angle = math.tau*i/8 + math.pi/8
        next_angle = angle+math.pi/4
        a = (rx*0.88*math.cos(angle), ry*0.88*math.sin(angle), 0)
        b = (radius*0.55*math.cos(angle), radius*0.55*math.sin(angle), -length*0.53)
        c = (radius*0.55*math.cos(next_angle), radius*0.55*math.sin(next_angle), -length*0.53)
        _cylinder(cone, a, b, 0.16*detail, "edge", facets=8)
        _cylinder(cone, a, c, 0.095*detail, "panel", facets=8)
        _cylinder(cone, b, c, 0.13*detail, "edge", facets=8)
        pipe_a = (radius*0.40*math.cos(angle), radius*0.40*math.sin(angle), -length*0.02)
        pipe_b = (radius*0.40*math.cos(angle), radius*0.40*math.sin(angle), -length*0.51)
        _cylinder(cone, pipe_a, pipe_b, 0.07*detail, "drive", facets=8)

    # Revolved, genuinely hollow nozzle: throat, expanding bell and rolled lip.
    profile = [(-0.48,0.38), (-0.56,0.49), (-0.66,0.68), (-0.80,0.88), (-0.96,1.0), (-1.0,1.0)]
    rings, inner = [], []
    for z, r in profile:
        rings.append(_ring(bell,z*length,r*radius,r*radius,48))
        inner.append(_ring(bell,z*length,(r-0.045)*radius,(r-0.045)*radius,48))
    for station in range(len(rings)-1):
        for i in range(48):
            j=(i+1)%48
            bell.face((rings[station][j],rings[station][i],rings[station+1][i],rings[station+1][j]), "drive")
            bell.face((inner[station][i],inner[station][j],inner[station+1][j],inner[station+1][i]), "dark")
    for i in range(48):
        j=(i+1)%48
        bell.face((rings[-1][j],rings[-1][i],inner[-1][i],inner[-1][j]), "edge")
    _disc(bell, (0,0,-length*0.51), (0,0,-1), radius*0.34, "drive_hot", 48)
    for z,r in ((-0.58,0.54), (-0.79,0.89), (-0.96,1.015)):
        _tube(bell,(0,0,z*length),(0,0,z*length-0.13*detail),r*radius,(r-0.03)*radius,"edge", facets=48, recessed=False)
    # Individual cooling ribs and evenly spaced clamps break the smooth bell.
    for i in range(24):
        angle=math.tau*i/24
        for (z0,r0),(z1,r1) in pairwise(profile[1:]):
            a=((r0*radius+0.045*detail)*math.cos(angle),(r0*radius+0.045*detail)*math.sin(angle),z0*length)
            b=((r1*radius+0.045*detail)*math.cos(angle),(r1*radius+0.045*detail)*math.sin(angle),z1*length)
            _cylinder(bell,a,b,0.055*detail,"panel",facets=6)
        _box(bell,(radius*math.cos(angle),radius*math.sin(angle),-length*0.98),
             (0.28*detail,0.28*detail,0.46*detail),"hull")
    return [tag(mesh_from("drive_cone",cone),"drive_cone"), tag(mesh_from("drive_bell",bell),"drive_bell")]


def build_pdcs(spec):
    """PDC bases intersect their hull surface, so no turrets float."""
    hull, weapons = spec["hull"], spec["weapons"]
    out, count = [], weapons["pdc_mounts"]
    for index in range(count):
        # Three opposed pairs: aft, shoulder and forward defensive arcs.
        band = (index // 2) % 3
        z = hull["length_m"] * (0.205, 0.465, 0.76)[band]
        angle = math.pi*(index % 2) + (math.pi/2 if band == 0 else 0) + (index//6)*math.pi/4
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
        _box(builder, turret, (1.05, 0.72, 1.05), "dark", basis)
        for side in (-1, 1):
            center = _add(turret, _scale(tangent, side*0.56))
            _box(builder, center, (0.18, 0.80, 1.18), "panel", basis)
            _cylinder(builder, center, _add(center,_scale(tangent,side*0.14)),0.29,"edge",facets=16)
        aim = _unit(_add(radial, (0, 0, 0.52)))
        _, u, v = _basis_for(aim)
        origin = _add(turret, _scale(aim,0.38))
        _cylinder(builder, turret, origin,0.38,"panel",facets=16)
        for barrel in range(6):
            offset = _scale(_add(_scale(u,math.cos(math.tau*barrel/6)),_scale(v,math.sin(math.tau*barrel/6))),0.23)
            start = _add(origin,offset)
            _tube(builder,start,_add(start,_scale(aim,1.55)),0.095,0.06,"edge",facets=10)
        for distance in (0.42,1.20):
            start=_add(origin,_scale(aim,distance))
            _tube(builder,start,_add(start,_scale(aim,0.15)),0.37,0.31,"hull",facets=16,recessed=False)
        sensor = _add(turret,(0,0,0.64))
        _box(builder,sensor,(0.37,0.38,0.22),"hull",basis)
        _disc(builder,_add(sensor,_scale(radial,0.20)),radial,0.095,"light")
        out.append(tag(mesh_from(f"pdc_{index + 1:02d}", builder), f"pdc_{index + 1:02d}"))
    return out


def build_tubes(spec):
    """Armored launch cassettes conform to the sloping forward hull."""
    hull, weapons = spec["hull"], spec["weapons"]
    count, out = weapons["torpedo_tubes"], []
    columns = min(4, max(1, math.ceil(count / 2)))
    rows = max(1, math.ceil(count/(2*columns)))
    for index in range(count):
        side = 1 if index % 2 == 0 else -1
        row, column = divmod(index//2, columns)
        z = hull["length_m"] * (weapons.get("tube_station", 0.70) - row * 0.10 / rows)
        rx, _ry = hull_radius_at(hull, z)
        spacing = min(1.65, rx * 0.95 / columns)
        x = (column - (columns - 1) / 2) * spacing
        half_length = hull["length_m"]*0.027/rows
        r0, s0 = hull_radius_at(hull,z-half_length)
        r1, s1 = hull_radius_at(hull,z+half_length)
        start = (x,side*(faceted_y_at_x(r0,s0,x)+0.25),z-half_length)
        end = (x,side*(faceted_y_at_x(r1,s1,x)+0.25),z+half_length)
        axis = _unit(_sub(end,start))
        normal = _unit((0,side,-side*axis[1]/axis[2]))
        center = _lerp(start,end,0.5)
        basis = ((side,0,0),normal,axis)
        builder = MeshBuilder()
        _box(builder,center,(spacing*0.94,0.55,half_length*2.08),"hull",basis)
        _box(builder,_add(center,_scale(normal,0.29)),(spacing*0.72,0.06,half_length*1.70),"dark",basis)
        for offset in (-0.23,0.23):
            _box(builder,_add(_add(center,_scale(normal,0.34)),(offset*spacing,0,0)),
                 (spacing*0.42,0.07,half_length*1.55),"panel",basis)
        _tube(builder,_sub(end,_scale(axis,0.35)),_add(end,_scale(axis,0.08)),
              spacing*0.32,spacing*0.24,"edge","dark",16)
        out.append(tag(mesh_from(f"tube_{index + 1:02d}", builder), f"tube_{index + 1:02d}"))
    return out


def _ellipsoid(builder, center, radii, material, rings=6, segments=12):
    rows = []
    for j in range(rings + 1):
        phi = math.pi * j / rings
        rows.append([builder.vertex(_add(center, (
            radii[0] * math.sin(phi) * math.cos(math.tau * i / segments),
            radii[1] * math.sin(phi) * math.sin(math.tau * i / segments),
            radii[2] * math.cos(phi)))) for i in range(segments)])
    for a, b in pairwise(rows):
        for i in range(segments):
            k = (i + 1) % segments
            builder.face((a[i], b[i], b[k], a[k]), material)


def _screen(builder, x, y, z, width=1.4, height=0.8):
    # Vertical readout on a console facing the open/front (+Y) side.
    _box(builder, (x, y, z), (width + 0.12, 0.14, height + 0.12), "dark")
    _box(builder, (x, y + 0.078, z), (width, 0.018, height), "screen")
    for row in range(6):
        _box(builder, (x - width * .17, y + .092, z + height * (.35 - row * .13)),
             (width * (.48 if row % 3 else .65), .008, .015), "light")
    for col in range(4):
        _box(builder, (x + width * (.2 + col * .055), y + .094, z - height * .1),
             (.035, .01, height * (.25 + col * .1)), "amber")


def _chair(builder, x, y, z):
    _cylinder(builder, (x, y, z), (x, y, z + .55), .18, "edge")
    _box(builder, (x, y, z + .58), (.78, .8, .18), "fabric")
    _box(builder, (x, y - .34, z + 1.10), (.8, .20, 1.1), "fabric")
    _box(builder, (x, y - .27, z + 1.72), (.5, .22, .3), "fabric")
    for side in (-1, 1):
        _box(builder, (x + side * .48, y, z + .92), (.14, .88, .14), "panel")
        _box(builder, (x + side * .21, y - .22, z + 1.15), (.07, .055, .83), "amber")
    _box(builder, (x, y + .62, z + .2), (.85, .36, .10), "edge")


def _person(builder, x, y, z, name, seated=False):
    """Original, static crew miniatures with boots, suits, harnesses and hair."""
    skin = "skin_dark" if name in ("Naomi", "Alex") else "skin"
    suit = "fabric" if name != "Amos" else "panel"
    hip = z + (.90 if not seated else .74)
    shoulder = hip + .52
    _ellipsoid(builder, (x, y, hip + .28), (.29 if name != "Amos" else .34, .18, .37), suit)
    _box(builder, (x, y, hip), (.46, .32, .20), suit)
    _cylinder(builder, (x, y, shoulder), (x, y, shoulder + .17), .09, skin)
    head = shoulder + .32
    _ellipsoid(builder, (x, y, head), (.17, .155, .22), skin)
    _ellipsoid(builder, (x, y - .025, head + .13), (.18, .15, .12 if name != "Naomi" else .20), "hair")
    if name in ("Holden", "Amos"):
        _ellipsoid(builder, (x, y + .09, head - .1), (.145, .075, .095), "hair")
    if name == "Naomi":
        for i in range(5):
            _ellipsoid(builder, (x + .1, y - .11, head + .04 + i * .055), (.13, .13, .13), "hair")
    for side in (-1, 1):
        legx = x + side * .14
        knee = (legx, y + (.4 if seated else .025), z + .44)
        ankle = (legx, knee[1], z + .13)
        _cylinder(builder, (legx, y, hip), knee, .115, suit)
        _cylinder(builder, knee, ankle, .095, suit)
        _box(builder, (legx, ankle[1] + .10, z + .10), (.23, .4, .20), "dark")
        elbow = (x + side * .36, y + .10, shoulder - .28)
        hand = (x + side * .30, y + (.48 if seated else .3), shoulder - .42)
        _cylinder(builder, (x + side * .24, y, shoulder - .04), elbow, .10, suit)
        _cylinder(builder, elbow, hand, .085, skin if name == "Amos" else suit)
        _ellipsoid(builder, hand, (.08, .08, .10), skin)
        _box(builder, (x + side * .16, y + .171, hip + .30), (.055, .035, .45), "amber")
    _box(builder, (x + .1, y + .2, hip + .42), (.09, .02, .065), "light")


def deck_layout(spec):
    """Bow-to-stern rooms, with enough headroom and clearance at BOTH ends."""
    hull = spec["hull"]
    total = sum(d["height_m"] for d in spec["decks"]) or 1
    ceiling = hull["length_m"] * .84
    result = []
    for index, deck in enumerate(spec["decks"]):
        height = deck["height_m"] * hull["length_m"] * .62 / total
        floor = ceiling - height
        r0, s0 = hull_radius_at(hull, floor)
        r1, s1 = hull_radius_at(hull, ceiling)
        result.append((index, deck, floor, height, min(r0, r1) * .79, min(s0, s1) * .79))
        ceiling = floor
    return result


def _cabinet(b, x, y, z, width=.8, height=1.8):
    """Recessed door, gasket, pull, vents and a positive locking latch."""
    _box(b, (x, y, z + height / 2), (width, .38, height), "dark")
    _box(b, (x, y + .20, z + height / 2), (width - .07, .05, height - .08), "panel")
    _box(b, (x + width * .3, y + .25, z + height * .52), (.04, .07, .24), "edge")
    _box(b, (x + width * .3, y + .29, z + height * .4), (.10, .04, .05), "amber")
    for i in range(5):
        _box(b, (x, y + .23, z + .12 + i * .05), (width * .55, .012, .015), "dark")
    _box(b, (x - width * .2, y + .235, z + height * .82), (width * .22, .015, .09), "white")


def _room_shell(b, rx, ry, z, height, index):
    """Rear pressure shell and service bays, open toward the cutaway camera."""
    back, top = -ry * .76, min(height - .16, 3.3)
    # Inset wall panels with visible seals, fasteners and overhead cable trays.
    count = max(3, int(rx * 1.3))
    pitch = rx * 1.38 / count
    for i in range(count):
        x = -rx * .69 + (i + .5) * pitch
        _box(b, (x, back + .095, z + top / 2), (pitch - .045, .055, top - .14), "panel")
        for dx in (-pitch * .39, pitch * .39):
            for zz in (.15, top - .15):
                _disc(b, (x + dx, back + .128, z + zz), (0, 1, 0), .024, "edge", 8)
        _box(b, (x, back + .16, z + top - .25), (pitch * .75, .13, .11), "dark")
        _box(b, (x, back + .24, z + top - .26), (pitch * .65, .02, .035), "light")
    for side in (-1, 1):
        # Knee-height side lining and sloping structural ribs.
        xx = side * rx * .72
        _box(b, (xx, back * .35, z + .40), (.12, ry * .78, .8), "hull")
        for yy in (back + .15, back * .35):
            _box(b, (xx, yy, z + top * .44), (.16, .18, top * .88), "edge")
            _cylinder(b, (xx, yy, z + top * .87), (xx * .80, yy, z + top), .09, "edge")
        for level in range(3):
            _cylinder(b, (side * rx * .62, back + .27, z + top - .10 - level * .10),
                      (side * .3, back + .27, z + top - .10 - level * .10), .025, "edge")
        _cylinder(b, (xx, back + .4, z + .92), (xx, .15, z + .92), .045, "amber")
    # Raised, segmented nonslip walkway with narrow drainage slots.
    for i in range(max(2, int(ry * 1.1 / .32))):
        yy = -ry * .45 + i * .32
        _box(b, (0, yy, z + .025), (min(1.35, rx * .55), .29, .035), "dark")
        for xx in (-.38, -.19, 0, .19, .38):
            _box(b, (xx, yy, z + .045), (.018, .22, .013), "edge")
    # Flush access cover beneath the ladder, with a hazard-marked coaming.
    lx = -rx * .65
    _box(b, (lx, -.3, z + .018), (.78, .82, .028), "dark")
    for dx in (-.4, .4):
        _box(b, (lx + dx, -.3, z + .05), (.055, .9, .045), "amber")
    # Deck identity expressed as small stencilled bars, plus emergency kit.
    for i in range(index + 1):
        _box(b, (-rx * .55 + i * .09, back + .14, z + top * .72), (.04, .018, .16), "white")
    _box(b, (rx * .58, back + .30, z + .65), (.32, .22, .5), "paint")
    _box(b, (rx * .58, back + .42, z + .65), (.20, .015, .045), "white")
    _box(b, (rx * .58, back + .43, z + .65), (.045, .015, .20), "white")


def _room_equipment(b, kind, index, rx, ry, z):
    back = -ry * .76
    if kind == "ops":
        # Flight instruments and tactile switch banks around the crash couch.
        for side in (-1, 1):
            _screen(b, side * rx * .30, back + .28, z + 2.18, rx * .42, .48)
            for row in range(3):
                for col in range(5):
                    _box(b, (side * rx * .45 + (col - 2) * .09, .63, z + .9 + row * .1),
                         (.05, .035, .035), "amber" if col == row else "white")
            _cylinder(b, (side * .44, .25, z + .92), (side * .44, .32, z + 1.18), .045, "dark")
        if index != 0:
            # Tactical plotting rings and contacts on the existing table.
            for radius in (.24, .45, .57):
                for i in range(48):
                    a, aa = math.tau * i / 48, math.tau * (i + 1) / 48
                    _cylinder(b, (radius * math.cos(a), 1.05 + radius * math.sin(a), z + 1.125),
                              (radius * math.cos(aa), 1.05 + radius * math.sin(aa), z + 1.125), .009, "amber", facets=4)
            _cabinet(b, -rx * .42, back + .4, z, .85, 1.8)
    elif kind == "crew":
        for side in (-1, 1):
            x = side * rx * .45
            for yy in (-1.35, .95):
                for dx in (-.68, .68):
                    _box(b, (x + dx, yy, z + 1.15), (.065, .065, 2.3), "edge")
            for level in (0, 1):
                zz = z + .48 + level * 1.15
                _box(b, (x, -1.31, zz + .43), (1.35, .07, .72), "hull")
                _box(b, (x, -1.26, zz + .70), (.65, .045, .045), "light")
                # Folded blanket seams and restraint straps.
                for dx in (-.4, 0, .4):
                    _box(b, (x + dx, .22, zz + .297), (.018, 1.04, .012), "fabric")
                _box(b, (x, .48, zz + .31), (1.24, .07, .02), "amber")
            _cabinet(b, side * .52, back + .35, z, .85, 2.1)
    elif kind == "galley":
        for side in (-1, 1):
            _cabinet(b, side * rx * .44, back + .30, z + 1.66, rx * .30, .68)
        # Sink inset, faucet, food canisters and restrained cups.
        sx = -rx * .30
        _box(b, (sx, back + .64, z + 1.121), (.65, .52, .018), "dark")
        _box(b, (sx, back + .64, z + 1.128), (.51, .39, .014), "edge")
        _cylinder(b, (sx, back + .32, z + 1.1), (sx, back + .32, z + 1.43), .028, "edge")
        _cylinder(b, (sx, back + .32, z + 1.43), (sx, back + .55, z + 1.43), .028, "edge")
        for i in range(5):
            xx = -rx * .12 + i * .19
            _cylinder(b, (xx, back + .45, z + 1.12), (xx, back + .45, z + 1.41), .07, "white", facets=16)
            _box(b, (xx, back + .526, z + 1.29), (.08, .01, .10), "paint")
        for x in (-rx * .4, 0, rx * .4):
            for j in range(3):
                _box(b, (x, back + 1.07, z + .16 + j * .29), (rx * .32, .02, .21), "dark")
                _box(b, (x, back + 1.1, z + .24 + j * .29), (rx * .21, .055, .025), "edge")
    elif kind == "machine":
        # Toolboard, drawer units, bench vise, drill press and spare pipework.
        _box(b, (0, back + .14, z + 1.72), (rx * 1.12, .08, .94), "dark")
        for i in range(12):
            x = (i - 5.5) * rx * .085
            _cylinder(b, (x, back + .23, z + 1.42), (x, back + .23, z + 1.85 + i % 3 * .08), .025, "edge")
            _tube(b, (x, back + .20, z + 1.91 + i % 3 * .08), (x, back + .26, z + 1.91 + i % 3 * .08), .065, .038, "edge", facets=10)
        for side in (-1, 1):
            for j in range(4):
                _box(b, (side * rx * .38, back + 1.44, z + .17 + j * .2), (rx * .30, .04, .16), "panel")
                _box(b, (side * rx * .38, back + 1.49, z + .2 + j * .2), (rx * .18, .045, .028), "edge")
        _box(b, (-.8, back + .9, z + 1.18), (.45, .4, .25), "dark")
        for dx in (-.22, .22):
            _box(b, (-.8 + dx, back + .9, z + 1.37), (.12, .43, .14), "edge")
        _cylinder(b, (.9, back + .6, z + 1.1), (.9, back + .6, z + 2), .065, "edge")
        _box(b, (.9, back + .78, z + 1.91), (.35, .6, .28), "paint")
        _cylinder(b, (.9, back + 1, z + 1.77), (.9, back + 1, z + 1.48), .025, "edge")
    else:
        for side in (-1, 1):
            # Flanged coolant lines, valve wheels and containment supports.
            xx = side * 1.5
            for zz in (.45, 1.5, 2.1):
                _tube(b, (xx, -.8, z + zz), (xx, -.8, z + zz + .09), .18, .1, "edge", facets=16)
            _cylinder(b, (xx, -.8, z + 1.1), (xx, -.45, z + 1.1), .06, "edge")
            _tube(b, (xx, -.45, z + 1.1), (xx, -.4, z + 1.1), .23, .19, "paint", facets=20)
            for i in range(4):
                a = math.tau * i / 4
                _cylinder(b, (xx, -.42, z + 1.1), (xx + .20 * math.cos(a), -.42, z + 1.1 + .20 * math.sin(a)), .016, "edge")
            _cylinder(b, (side * .8, 0, z + 1.85), (side * 1.2, .15, z + .12), .09, "edge")
            _cabinet(b, side * rx * .57, back + .40, z, .8, 2.2)


def build_decks(spec):
    """Furnished room modules; furniture/crew travel with their deck on reveal.

    A compact interpretation of the TV sets, not a canonical floor plan.
    See docs/INTERIOR-REFERENCES.md for the production research.
    """
    out = []
    for index, deck, z, height, rx, ry in deck_layout(spec):
        b = MeshBuilder()
        name = f"deck_{index + 1:02d}_{deck['kind']}"
        add_faceted_shell(b, [(z - .16, rx, ry), (z, rx, ry)], "panel")
        # Floor tiles, luminous edge strips and rear ribs leave a cutaway side.
        for x in range(-int(rx * .7), int(rx * .7) + 1):
            extent = faceted_y_at_x(rx, ry, x) * 1.96
            _box(b, (x, 0, z + .012), (.025, extent, .015), "dark")
        for y in range(-int(ry * .7), int(ry * .7) + 1):
            extent = faceted_y_at_x(ry, rx, y) * 1.96
            _box(b, (0, y, z + .014), (extent, .025, .015), "dark")
        for side in (-1, 1):
            _box(b, (side * rx * .76, 0, z + .025), (.045, ry * .9, .04), "screen")
        back = -ry * .76
        _box(b, (0, back, z + 1.12), (rx * 1.38, .15, 2.24), "hull")
        for x in (-rx * .64, 0, rx * .64):
            _box(b, (x, back + .08, z + 1.2), (.12, .18, 2.4), "edge")
        _box(b, (0, back + .1, z + 2.28), (rx * 1.26, .12, .06), "light")
        _room_shell(b, rx, ry, z, height, index)
        # Interdeck ladder / hatch and a short safety railing.
        lx = -rx * .65
        for dx in (-.28, .28):
            _cylinder(b, (lx + dx, -.3, z + .1), (lx + dx, -.3, z + height - .1), .045, "edge")
        for i in range(max(1, int(height / .32))):
            _cylinder(b, (lx - .28, -.3, z + .16 + i * .32), (lx + .28, -.3, z + .16 + i * .32), .035, "amber")
        for x in (-rx * .55, rx * .55):
            _cylinder(b, (x, ry * .60, z), (x, ry * .60, z + .88), .045, "edge")
        _cylinder(b, (-rx * .55, ry * .60, z + .88), (rx * .55, ry * .60, z + .88), .045, "edge")
        kind = deck["kind"]
        crew = []
        if kind == "ops":
            _chair(b, 0, -.3, z)
            _screen(b, 0, back + .22, z + 1.38, min(2.4, rx), 1.0)
            for side in (-1, 1):
                _box(b, (side * rx * .45, -.25, z + .7), (.75, 1.7, 1.3), "hull")
                _screen(b, side * rx * .45, .62, z + 1.4, .7, .65)
            if index == 0:
                crew = [("Alex", 0, -.22, True)]
            else:
                _box(b, (0, 1.05, z + .5), (.45, .45, 1), "edge")
                _box(b, (0, 1.05, z + 1.03), (2.8, 1.4, .12), "dark")
                _box(b, (0, 1.05, z + 1.10), (2.6, 1.2, .015), "screen")
                for i in range(9):
                    _box(b, (-1.1 + i * .27, 1.05, z + 1.112), (.015, 1.05, .012), "light")
                crew = [("Holden", 1.8, .75, False)]
        elif kind == "crew":
            for side in (-1, 1):
                for level in (0, 1):
                    x, zz = side * rx * .45, z + .48 + level * 1.15
                    _box(b, (x, -.2, zz), (1.35, 2.25, .15), "edge")
                    _box(b, (x, -.2, zz + .14), (1.22, 2.12, .18), "fabric")
                    _box(b, (x, -.85, zz + .26), (.9, .45, .16), "white")
                    _box(b, (x, .22, zz + .25), (1.23, 1.1, .08), "paint")
            _screen(b, 0, back + .2, z + 2.55, 1, .6)
        elif kind == "galley":
            _box(b, (0, back + .6, z + .52), (rx * 1.22, .9, 1.04), "panel")
            _box(b, (0, back + .6, z + 1.07), (rx * 1.25, 1, .09), "edge")
            for x in (-rx * .4, 0, rx * .4):
                for j in range(3):
                    _box(b, (x, back + 1.06, z + .2 + j * .29), (rx * .35, .025, .025), "edge")
            _tube(b, (0, back + .12, z + 1.8), (0, back + .3, z + 1.8), .57, .49, "light", recessed=False)
            for i in range(12):
                a = i * 2.4
                _ellipsoid(b, (.36 * math.cos(a), back + .23, z + 1.8 + .36 * math.sin(a)), (.12, .08, .09), "plant")
            _box(b, (rx * .35, back + .6, z + 1.4), (.48, .55, .6), "dark")
            _box(b, (rx * .35, back + .89, z + 1.45), (.32, .04, .12), "light")
            _cylinder(b, (0, .6, z), (0, .6, z + .86), .2, "edge")
            _cylinder(b, (0, .6, z + .86), (0, .6, z + .97), 1.35, "panel", facets=6)
            for i in range(4):
                a = math.tau * i / 4
                cx, cy = 1.75 * math.cos(a), .6 + 1.75 * math.sin(a)
                start = len(b.verts)
                _chair(b, cx, cy, z)
                # Chairs face inward around the galley table.
                angle = a + math.pi / 2
                for j in range(start, len(b.verts)):
                    vx, vy, vz = b.verts[j]
                    dx, dy = vx - cx, vy - cy
                    b.verts[j] = (cx + dx * math.cos(angle) - dy * math.sin(angle),
                                  cy + dx * math.sin(angle) + dy * math.cos(angle), vz)
                _cylinder(b, (.8 * math.cos(a), .6 + .8 * math.sin(a), z + .97),
                          (.8 * math.cos(a), .6 + .8 * math.sin(a), z + 1.10), .13, "white")
        elif kind == "machine":
            _box(b, (0, back + .8, z + .48), (rx * 1.18, 1.25, .95), "paint")
            _box(b, (0, back + .8, z + 1), (rx * 1.25, 1.35, .13), "edge")
            for i in range(8):
                x = (i - 3.5) * rx * .13
                _box(b, (x, back + .17, z + 1.7), (.055, .08, .4 + (i % 3) * .1), "amber")
            for side in (-1, 1):
                _box(b, (side * rx * .53, 1, z + .52), (1.2, 1.2, 1.04), "hull")
                _box(b, (side * rx * .53, 1, z + 1.06), (1.05, 1.05, .08), "amber")
            crew = [("Amos", .4, back + 1.9, False)]
        else:
            # Contained reactor vessel, coolant rings, manifold and service consoles.
            _cylinder(b, (0, 0, z + .1), (0, 0, z + 2.1), .9, "dark", facets=24)
            for level in range(5):
                zz = z + .32 + level * .4
                _tube(b, (0, 0, zz), (0, 0, zz + .12), 1.03, .9,
                      "screen" if level % 2 else "edge", facets=24, recessed=False)
            for side in (-1, 1):
                for i in range(3):
                    x = side * (1.5 + i * .32)
                    _cylinder(b, (x, -.8, z + .15), (x, -.8, z + 2.35), .10, "amber" if i == 0 else "edge")
                _screen(b, side * rx * .32, back + .2, z + 1.55, 1.2, .9)
            crew = [("Naomi", 1.7, .9, False)]
        _room_equipment(b, kind, index, rx, ry, z)
        obj = tag(mesh_from(name, b), name)
        bevel = obj.modifiers.new("Machined edge highlights", "BEVEL")
        bevel.width, bevel.segments = .012, 2
        obj["assembly_kind"] = "deck"
        obj["interior_revision"] = 2
        # Metadata is in browser axes (Y up), independent of Blender's Z up.
        obj["assembly_offset"] = [0, (2.5 - index) * 2.8, -1.5]
        obj["deck_label"] = deck["name"]
        obj["deck_index"] = index
        obj["deck_station"] = z
        out.append(obj)
        available_crew = {member["name"] for member in spec["crew"]}
        for crew_name, x, y, seated in crew:
            if crew_name not in available_crew:
                continue
            person = MeshBuilder()
            _person(person, x, y, z + .025, crew_name, seated)
            person_name = f"crew_{crew_name.lower()}"
            figure = tag(mesh_from(person_name, person), person_name)
            figure["assembly_kind"] = "crew"
            figure["assembly_offset"] = list(obj["assembly_offset"])
            figure["crew_name"] = crew_name
            figure["deck_index"] = index
            out.append(figure)
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
        make("hull_graphite", (0.075, 0.090, 0.108, 1), 0.52, 0.48),
        make("armor_panel", (0.25, 0.28, 0.30, 1), 0.42, 0.50),
        make("recess_black", (0.025, 0.032, 0.045, 1), 0.42, 0.32),
        make("drive_ceramic", (0.16, 0.13, 0.11, 1), 0.72, 0.38),
        make("drive_core", (0.10, 0.18, 0.34, 1), 0.22, 0.24, ((0.20, 0.48, 1.0, 1), 1.5)),
        make("exposed_alloy", (0.34, 0.38, 0.40, 1), 0.78, 0.34),
        make("oxide_identification", (0.34, 0.068, 0.027, 1), 0.25, 0.58),
        make("ceramic_markings", (0.62, 0.65, 0.63, 1), 0.15, 0.65),
        make("navigation_lights", (0.48, 0.65, 0.8, 1), 0.15, 0.25, ((0.55, 0.76, 1.0, 1), 2.0)),
        make("console_cyan", (0.015, 0.12, 0.18, 1), 0.3, 0.3, ((0.02, 0.42, 0.65, 1), 0.65)),
        make("safety_amber", (0.8, 0.32, 0.045, 1), 0.2, 0.5),
        make("crash_couch_and_flight_suit", (0.045, 0.085, 0.12, 1), 0.05, 0.92),
        make("crew_skin", (0.55, 0.30, 0.19, 1), 0.0, 0.9),
        make("crew_skin_warm", (0.29, 0.13, 0.07, 1), 0.0, 0.9),
        make("crew_hair", (0.019, 0.013, 0.012, 1), 0.0, 0.97),
        make("galley_greens", (0.06, 0.28, 0.08, 1), 0.0, 0.8),
    )
    # Locally bundled online PBR images are embedded in the GLB, so rooms also
    # work offline. Separate interior copies preserve the exterior palette.
    interior = list(materials)
    for key, asset in (("panel", "Metal032"), ("edge", "Metal032"),
                       ("fabric", "Fabric032")):
        slot = MATERIAL_KEYS.index(key)
        material = materials[slot].copy()
        material.name = "interior_" + key
        nodes, links = material.node_tree.nodes, material.node_tree.links
        shader = nodes["Principled BSDF"]
        for suffix, socket in (("Color", "Base Color"), ("Roughness", "Roughness"),
                               ("NormalGL", "Normal")):
            texture = nodes.new("ShaderNodeTexImage")
            texture.image = bpy.data.images.load(str(Path(__file__).parent / "textures" /
                                                    f"{asset}_1K-JPG_{suffix}.jpg"), check_existing=True)
            if suffix != "Color":
                texture.image.colorspace_settings.name = "Non-Color"
            if suffix == "NormalGL":
                normal = nodes.new("ShaderNodeNormalMap")
                normal.inputs["Strength"].default_value = .32 if key == "fabric" else .22
                links.new(texture.outputs["Color"], normal.inputs["Color"])
                links.new(normal.outputs["Normal"], shader.inputs[socket])
            elif suffix == "Color":
                tint = nodes.new("ShaderNodeMix")
                tint.data_type = "RGBA"
                tint.blend_type = "MULTIPLY"
                tint.inputs[0].default_value = 1
                tint.inputs[7].default_value = (
                    (.07, .12, .17, 1) if key == "fabric" else (.46, .51, .54, 1))
                links.new(texture.outputs["Color"], tint.inputs[6])
                links.new(tint.outputs[2], shader.inputs[socket])
            else:
                links.new(texture.outputs["Color"], shader.inputs[socket])
        interior[slot] = material
    for obj in objects:
        is_room = obj.get("assembly_kind") in ("deck", "crew")
        for material in interior if is_room else materials:
            obj.data.materials.append(material)
        if is_room:
            # Meter-scaled planar coordinates, independently projected on each
            # face to avoid stretched grain on thin cabinet and chair edges.
            uv = obj.data.uv_layers.new(name="SurfaceMeters")
            for polygon in obj.data.polygons:
                axis = max(range(3), key=lambda i: abs(polygon.normal[i]))
                axes = ((1, 2), (0, 2), (0, 1))[axis]
                for loop_index in polygon.loop_indices:
                    point = obj.data.vertices[obj.data.loops[loop_index].vertex_index].co
                    uv.data[loop_index].uv = (point[axes[0]] * 2, point[axes[1]] * 2)


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


def frame_viewports(span, center):
    """Make the generated model readable when opened in the live Blender UI."""
    from mathutils import Vector

    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            space = area.spaces.active
            space.clip_end = max(2000, span*10)
            space.shading.type = "MATERIAL"
            space.overlay.show_overlays = False
            space.region_3d.view_location = Vector(center)
            space.region_3d.view_distance = span*1.65
            space.region_3d.view_rotation = Vector((1.45,2.0,0.76)).to_track_quat("Z","Y")


def add_lights(span, center):
    from mathutils import Vector

    def point_at(obj):
        obj.rotation_euler = (Vector(center) - obj.location).to_track_quat("-Z", "Y").to_euler()

    key = bpy.data.lights.new("key", type="AREA")
    key.energy, key.shape, key.size = span * span * 28, "DISK", span * 0.8
    key_obj = bpy.data.objects.new("key", key)
    bpy.context.collection.objects.link(key_obj)
    key_obj.location = _add(center, (span * 0.85, span * 1.20, span * 0.80))
    point_at(key_obj)
    rim = bpy.data.lights.new("rim", type="AREA")
    rim.energy, rim.shape, rim.size = span * span * 24, "RECTANGLE", span * 0.6
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
    frame_viewports(span, center)
    if payload.get("blend"):
        bpy.ops.wm.save_as_mainfile(filepath=payload["blend"])
    if payload.get("out"):
        bpy.ops.export_scene.gltf(filepath=payload["out"], export_format="GLB", export_extras=True, export_apply=True)
        print(f"wrote {payload['out']} ({len(objects)} parts)")
    if render := payload.get("render"):
        from mathutils import Quaternion, Vector

        scene = bpy.context.scene
        # A diagonal three-quarter presentation fills a landscape frame and
        # shows both the forward armor and the recessed engine throat.
        cam = scene.camera
        cam.constraints.clear()
        cam.location = _add(center,(span*1.45,span*2.0,-span*0.50))
        rotation = (Vector(center)-cam.location).to_track_quat("-Z","Y")
        cam.rotation_euler = (rotation @ Quaternion((0,0,1),math.radians(-58))).to_euler()
        cam.data.lens = 64 if render["resolution"][0] > render["resolution"][1] else 40
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
