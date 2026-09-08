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
MATERIAL_KEYS = ("hull", "panel", "dark", "drive", "drive_hot", "edge", "paint", "white", "light")


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
    return [tag(mesh_from("hull_body", builder), "hull_body")]


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
        z = hull["length_m"] * (0.70 - row * 0.10 / rows)
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
        make("hull_graphite", (0.075, 0.090, 0.108, 1), 0.52, 0.48),
        make("armor_panel", (0.25, 0.28, 0.30, 1), 0.42, 0.50),
        make("recess_black", (0.025, 0.032, 0.045, 1), 0.42, 0.32),
        make("drive_ceramic", (0.16, 0.13, 0.11, 1), 0.72, 0.38),
        make("drive_core", (0.10, 0.18, 0.34, 1), 0.22, 0.24, ((0.20, 0.48, 1.0, 1), 1.5)),
        make("exposed_alloy", (0.34, 0.38, 0.40, 1), 0.78, 0.34),
        make("oxide_identification", (0.34, 0.068, 0.027, 1), 0.25, 0.58),
        make("ceramic_markings", (0.62, 0.65, 0.63, 1), 0.15, 0.65),
        make("navigation_lights", (0.48, 0.65, 0.8, 1), 0.15, 0.25, ((0.55, 0.76, 1.0, 1), 2.0)),
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
