"""Pure geometry checks for the Blender-only ship builder."""

import ast
import math
from itertools import pairwise
from pathlib import Path

import pytest


def hull_profile():
    """Load only the pure helper without importing Blender's ``bpy`` module."""
    source = Path("src/rocinante/blend/build_ship.py").read_text()
    module = ast.parse(source)
    function = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "hull_profile"
    )
    namespace = {"math": math, "pairwise": pairwise, "FACETS": 8}
    exec(  # noqa: S102 -- test-only extraction avoids importing Blender's bpy module.
        compile(ast.Module(body=[function], type_ignores=[]), "build_ship.py", "exec"), namespace
    )
    return namespace["hull_profile"]


def hull_radius_at():
    """Load the two pure profile helpers without importing Blender."""
    source = Path("src/rocinante/blend/build_ship.py").read_text()
    module = ast.parse(source)
    functions = [
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name in {
            "hull_profile", "hull_radius_at", "faceted_surface_distance", "faceted_y_at_x"
        }
    ]
    namespace = {"math": math, "pairwise": pairwise, "FACETS": 8}
    exec(  # noqa: S102 -- test-only extraction avoids importing Blender's bpy module.
        compile(ast.Module(body=functions, type_ignores=[]), "build_ship.py", "exec"), namespace
    )
    return namespace


def test_hull_profile_has_a_broad_working_hull_and_a_chamfered_prow():
    profile = hull_profile()({"length_m": 100.0, "beam_m": 12.0, "taper": 0.7})

    assert len(profile) == 8
    assert profile[2] == pytest.approx((28.0, 6.0))
    assert profile[-1] == pytest.approx((100.0, 0.42))
    assert all(after[0] > before[0] for before, after in pairwise(profile))
    # The final three hard changes in radius are intentional shoulder, chamfer,
    # and cockpit-face planes rather than a rounded rocket ogive.
    assert all(after[1] < before[1] for before, after in pairwise(profile[3:]))


def test_local_hull_radius_keeps_decks_and_flush_mounts_inside_the_hull():
    radius_at = hull_radius_at()["hull_radius_at"]
    hull = {"length_m": 46.0, "beam_m": 23.0, "taper": 0.42}

    mid_x, mid_y = radius_at(hull, 46.0 * 0.46)
    nose_x, nose_y = radius_at(hull, 46.0 * 0.90)

    assert mid_x == pytest.approx(11.04)
    assert mid_y == pytest.approx(mid_x * 0.74)
    assert nose_x < mid_x
    assert nose_y < mid_y


def test_mounts_use_the_actual_octagonal_face_instead_of_its_outer_ellipse():
    helpers = hull_radius_at()
    surface = helpers["faceted_surface_distance"]
    y_at_x = helpers["faceted_y_at_x"]
    rx, ry = 10.0, 7.4

    assert surface(rx, ry, (0.0, 1.0)) == pytest.approx(ry * math.cos(math.pi / 8))
    assert y_at_x(rx, ry, 0.0) == pytest.approx(ry * math.cos(math.pi / 8))
    assert y_at_x(rx, ry, rx * math.cos(math.pi / 8)) == pytest.approx(ry * math.sin(math.pi / 8))
