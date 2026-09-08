"""Structured difference between two rocket designs.

This is what makes the demo legible. A `.ork` is a zip; a byte diff says
nothing. Comparing the specs says "the fins swept 12 mm and the body grew
40 mm", and it names the parts the 3D viewer should highlight.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from rocinante.ship import ShipSpec
from rocinante.sim.base import SimResult
from rocinante.spec import RocketSpec

# Field paths that map onto a mesh name in build_rocket.py.
PART_OF_PREFIX = {
    "nose": "nose",
    "fins": "fin_*",
    "body": "tube_*",
    "motor": "motor",
    "nose_ballast_kg": "nose",
}

# The same idea for the ship, against build_ship.py's naming convention. These
# strings are what the 3D viewer highlights, so they have to match the tags
# build_ship.py writes into `rocinante_part`.
SHIP_PART_OF_PREFIX = {
    "hull": "hull_body",
    "drive": "drive_*",
    "weapons": "tube_*",
    "decks": "deck_*",
    "crew": None,
    "stores_t": None,
}


class FieldChange(BaseModel):
    path: str
    before: Any
    after: Any
    part: str | None = None

    def human(self) -> str:
        if isinstance(self.before, (int, float)) and isinstance(self.after, (int, float)):
            delta = self.after - self.before
            return f"{self.path}: {self.before:.4g} -> {self.after:.4g} ({delta:+.4g})"
        return f"{self.path}: {self.before} -> {self.after}"


class SpecDiff(BaseModel):
    changes: list[FieldChange] = []

    @property
    def changed_parts(self) -> list[str]:
        return sorted({c.part for c in self.changes if c.part})

    def markdown(self) -> str:
        if not self.changes:
            return "_No geometry change._"
        return "\n".join(f"- `{c.human()}`" for c in self.changes)


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            out.update(_flatten(v, f"{prefix}.{k}" if prefix else k))
        return out
    if isinstance(value, list):
        out = {}
        for i, v in enumerate(value):
            out.update(_flatten(v, f"{prefix}[{i}]"))
        return out
    return {prefix: value}


def diff_specs(before: RocketSpec, after: RocketSpec, tolerance: float = 1e-9) -> SpecDiff:
    a = _flatten(before.model_dump(mode="json"))
    b = _flatten(after.model_dump(mode="json"))

    changes: list[FieldChange] = []
    for path in sorted(set(a) | set(b)):
        if path.startswith(("rationale", "name")):
            continue
        old, new = a.get(path), b.get(path)
        if isinstance(old, (int, float)) and isinstance(new, (int, float)):
            if abs(old - new) <= tolerance:
                continue
        elif old == new:
            continue
        root = path.split(".")[0].split("[")[0]
        changes.append(FieldChange(path=path, before=old, after=new, part=PART_OF_PREFIX.get(root)))
    return SpecDiff(changes=changes)


def diff_results(before: SimResult, after: SimResult) -> str:
    """One line a human reads before they approve or reject."""
    return (
        f"apogee {before.apogee_m:.0f} -> {after.apogee_m:.0f} m "
        f"({after.apogee_m - before.apogee_m:+.0f}) | "
        f"stability {before.stability_margin_cal:.2f} -> {after.stability_margin_cal:.2f} cal "
        f"({after.stability_margin_cal - before.stability_margin_cal:+.2f})"
    )


def diff_ships(before: ShipSpec, after: ShipSpec, tolerance: float = 1e-9) -> SpecDiff:
    """Compare two ship revisions as designs.

    Same machinery as `diff_specs`, a different part map. Kept separate rather
    than generalised: the two part conventions are the thing most likely to
    drift, and a shared function would hide that.
    """
    a = _flatten(before.model_dump(mode="json"))
    b = _flatten(after.model_dump(mode="json"))

    changes: list[FieldChange] = []
    for path in sorted(set(a) | set(b)):
        if path.startswith(("rationale", "name")):
            continue
        old, new = a.get(path), b.get(path)
        if isinstance(old, (int, float)) and isinstance(new, (int, float)):
            if abs(old - new) <= tolerance:
                continue
        elif old == new:
            continue
        root = path.split(".")[0].split("[")[0]
        part = SHIP_PART_OF_PREFIX.get(root)
        # A weapons change only moves geometry when it changes the tube count.
        if root == "weapons" and "torpedo_tubes" not in path:
            part = None
        changes.append(FieldChange(path=path, before=old, after=new, part=part))
    return SpecDiff(changes=changes)


def diff_derived(before: ShipSpec, after: ShipSpec) -> str:
    """The line under the 3D diff. Every number here is computed, not claimed."""
    a, b = before.derived(), after.derived()
    moved = [
        f"{k.replace('_', ' ')} {a[k]:,.1f} -> {b[k]:,.1f} ({b[k] - a[k]:+,.1f})"
        for k in a
        if abs(a[k] - b[k]) > 1e-9
    ]
    return " | ".join(moved) if moved else "nothing derived moved"
