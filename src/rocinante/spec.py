"""The rocket design contract.

This module is the most important boundary in the project. The model emits a
`RocketSpec` and nothing else. It never writes `.ork` XML and never writes
Blender geometry by hand. Everything downstream -- the simulator, the mesh
builder, the diff -- reads this one structure.

Keep it small. Every field you add here is a field the model can get wrong.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class NoseShape(str, Enum):
    OGIVE = "ogive"
    CONICAL = "conical"
    ELLIPSOID = "ellipsoid"
    PARABOLIC = "parabolic"
    HAACK = "haack"


class FinCrossSection(str, Enum):
    SQUARE = "square"
    ROUNDED = "rounded"
    AIRFOIL = "airfoil"


class NoseCone(BaseModel):
    shape: NoseShape = NoseShape.OGIVE
    length_m: float = Field(gt=0, le=1.5)
    base_radius_m: float = Field(gt=0, le=0.2)
    wall_thickness_m: float = Field(default=0.002, gt=0)
    # Only read for OGIVE / HAACK / PARABOLIC. 1.0 is a tangent ogive.
    shape_parameter: float = Field(default=1.0, ge=0.0, le=1.0)
    material: str = "Cardboard"


class BodyTube(BaseModel):
    name: str = "Body tube"
    length_m: float = Field(gt=0, le=3.0)
    outer_radius_m: float = Field(gt=0, le=0.2)
    wall_thickness_m: float = Field(default=0.0015, gt=0)
    material: str = "Cardboard"


class FinSet(BaseModel):
    count: int = Field(default=3, ge=3, le=8)
    root_chord_m: float = Field(gt=0, le=0.5)
    tip_chord_m: float = Field(ge=0, le=0.5)
    # Semi-span, measured from the body tube surface outward.
    height_m: float = Field(gt=0, le=0.3)
    # Leading-edge sweep distance along the body axis. 0 is an unswept fin.
    sweep_m: float = Field(default=0.0, ge=0)
    thickness_m: float = Field(default=0.003, gt=0)
    cross_section: FinCrossSection = FinCrossSection.SQUARE
    # Distance forward from the aft end of the tube the fins are mounted on.
    offset_from_aft_m: float = Field(default=0.0, ge=0)
    material: str = "Plywood"


class Motor(BaseModel):
    """Identifies a motor from the OpenRocket thrustcurve database."""

    designation: str = "E12"
    manufacturer: str = "Estes"
    diameter_mm: float = Field(default=24.0, gt=0)
    length_mm: float = Field(default=70.0, gt=0)
    # Ejection delay, the "-6" in E12-6. Fires the recovery charge after burnout.
    delay_s: float = Field(default=6.0, ge=0)


class Recovery(BaseModel):
    chute_diameter_m: float = Field(default=0.3, gt=0)
    drag_coefficient: float = Field(default=0.8, gt=0)
    deploy_at_apogee: bool = True


class RocketSpec(BaseModel):
    """A complete, buildable rocket. One design iteration."""

    name: str = "Untitled"
    nose: NoseCone
    body: list[BodyTube] = Field(min_length=1)
    fins: FinSet
    motor: Motor = Motor()
    recovery: Recovery = Recovery()
    # Ballast in the nose, the cheapest way for the agent to move the CG forward.
    nose_ballast_kg: float = Field(default=0.0, ge=0)

    # Why this iteration differs from the last one. Not physics -- this becomes
    # the review session comment a human reads in Kord.
    rationale: str = ""

    @model_validator(mode="after")
    def _tip_not_wider_than_root(self) -> RocketSpec:
        if self.fins.tip_chord_m > self.fins.root_chord_m:
            raise ValueError("fin tip chord must not exceed root chord")
        return self

    @property
    def total_length_m(self) -> float:
        return self.nose.length_m + sum(t.length_m for t in self.body)

    @property
    def max_radius_m(self) -> float:
        return max([self.nose.base_radius_m, *(t.outer_radius_m for t in self.body)])

    @property
    def caliber_m(self) -> float:
        """Body diameter. Stability margin is quoted in these."""
        return self.max_radius_m * 2


def baseline_torpedo() -> RocketSpec:
    """A segmented, torpedo-shaped demo round at model scale (not flight validated)."""
    return RocketSpec(
        name="Torpedo Mk VI",
        nose=NoseCone(shape=NoseShape.ELLIPSOID, length_m=0.10, base_radius_m=0.028),
        body=[BodyTube(name=name, length_m=length, outer_radius_m=0.028)
              for name, length in [("Guidance", .05), ("Payload", .10),
                                   ("Avionics", .055), ("Power", .055),
                                   ("Coupler", .03), ("Booster", .16)]],
        fins=FinSet(count=4, root_chord_m=.065, tip_chord_m=.028, height_m=.018,
                    sweep_m=.025, thickness_m=.002, offset_from_aft_m=.012,
                    cross_section=FinCrossSection.AIRFOIL),
        motor=Motor(designation="E12", diameter_mm=24, length_mm=70),
    )


def json_schema() -> dict:
    """The schema handed to the model as a structured-output / tool contract."""
    return RocketSpec.model_json_schema()
