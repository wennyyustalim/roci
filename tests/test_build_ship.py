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
    namespace = {"math": math}
    exec(  # noqa: S102 -- test-only extraction avoids importing Blender's bpy module.
        compile(ast.Module(body=[function], type_ignores=[]), "build_ship.py", "exec"), namespace
    )
    return namespace["hull_profile"]


def test_hull_profile_is_continuous_from_barrel_to_nose_tip():
    profile = hull_profile()({"length_m": 100.0, "beam_m": 12.0, "taper": 0.7}, steps=24)
    join = 100.0 * 0.72
    join_points = [radius for z, radius in profile if z == pytest.approx(join)]

    assert len(join_points) == 1
    assert join_points[0] == pytest.approx(12.0 / 2 * 0.7)
    assert profile[-1] == pytest.approx((100.0, 0.0))
    assert all(after[0] > before[0] for before, after in pairwise(profile))
    assert all(after[1] <= before[1] + 1e-12 for before, after in pairwise(profile[-25:]))
