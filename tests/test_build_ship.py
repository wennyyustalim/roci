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


def test_hull_profile_has_a_narrow_waist_armored_shoulders_and_blunt_prow():
    profile = hull_profile()({"length_m": 100.0, "beam_m": 12.0, "taper": 0.7})

    assert profile[4] == pytest.approx((29.0, 3.3))
    assert profile[6] == pytest.approx((38.0, 6.0))
    assert profile[7] == pytest.approx((53.0, 6.0))
    assert profile[-1] == pytest.approx((94.0, 6.0*0.7*0.63))
    assert all(after[0] > before[0] for before, after in pairwise(profile))
    assert max(radius for _, radius in profile) == 6.0
    # The central armor is wider than both the machinery waist and bow.
    assert profile[4][1] < profile[6][1] > profile[-1][1]
    assert all(after[1] < before[1] for before, after in pairwise(profile[9:]))


def test_local_hull_radius_keeps_decks_and_flush_mounts_inside_the_hull():
    radius_at = hull_radius_at()["hull_radius_at"]
    hull = {"length_m": 46.0, "beam_m": 23.0, "taper": 0.42}

    mid_x, mid_y = radius_at(hull, 46.0 * 0.46)
    nose_x, nose_y = radius_at(hull, 46.0 * 0.90)

    assert mid_x == pytest.approx(11.5)
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
