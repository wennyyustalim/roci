"""The spacecraft design contract.

`RocketSpec` in spec.py is the torpedo. This is the ship that carries them.

Same rule as spec.py: the model emits a `ShipSpec` and nothing else. It never
writes Blender geometry and never writes the numbers below by hand -- every
derived property here is computed from the spec, so a refit cannot lie about
its own consequences.

Kept in its own module so the geometry track and the systems track can both
edit at once without fighting over spec.py.
"""

from __future__ import annotations

import math
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from rocinante.spec import RocketSpec, baseline_torpedo

G0 = 9.80665  # m/s^2, standard gravity. Accelerations are quoted in these.


class DeckKind(str, Enum):
    OPS = "ops"
    CREW = "crew"
    GALLEY = "galley"
    MACHINE = "machine"
    ENGINEERING = "engineering"
    CARGO = "cargo"


class Hull(BaseModel):
    """The pressure hull. A tapered body, decks stacked along the thrust axis."""

    length_m: float = Field(default=46.0, gt=5, le=500)
    beam_m: float = Field(default=23.0, gt=2, le=200)
    # Nose radius as a fraction of max radius. 1.0 is a cylinder.
    taper: float = Field(default=0.42, gt=0.05, le=1.0)
    deck_count: int = Field(default=6, ge=1, le=40)
    armor_cm: float = Field(default=5.5, ge=0, le=60)
    # Structural mass per square metre of hull skin, before armor.
    skin_kg_m2: float = Field(default=180.0, gt=0)

    @property
    def max_radius_m(self) -> float:
        return self.beam_m / 2

    @property
    def skin_area_m2(self) -> float:
        """Lateral area of the tapered body, as a frustum."""
        r_aft, r_fwd = self.max_radius_m, self.max_radius_m * self.taper
        slant = math.hypot(self.length_m, r_aft - r_fwd)
        return math.pi * (r_aft + r_fwd) * slant

    @property
    def structure_t(self) -> float:
        armor_kg_m2 = self.armor_cm * 0.01 * 7850.0  # steel-ish
        return self.skin_area_m2 * (self.skin_kg_m2 + armor_kg_m2) / 1000.0


class EpsteinDrive(BaseModel):
    """The fusion drive. Exhaust velocity is what buys delta-v; thrust buys g."""

    exhaust_velocity_km_s: float = Field(default=1300.0, gt=0)
    max_thrust_kn: float = Field(default=372_600.0, gt=0)
    cone_length_m: float = Field(default=11.0, gt=0)
    cone_radius_m: float = Field(default=6.5, gt=0)
    propellant_t: float = Field(default=1000.0, gt=0)
    dry_t: float = Field(default=420.0, gt=0)

    @property
    def exhaust_velocity_ms(self) -> float:
        return self.exhaust_velocity_km_s * 1000.0

    @property
    def mass_flow_kg_s(self) -> float:
        """Propellant burned per second at full throttle."""
        return self.max_thrust_kn * 1000.0 / self.exhaust_velocity_ms


class Weapons(BaseModel):
    railgun: bool = True
    railgun_t: float = Field(default=60.0, ge=0)
    torpedo_tubes: int = Field(default=4, ge=0, le=32)
    # Where the launch tubes mount, as a fraction of hull length from the
    # stern: 0.9 is right at the bow, 0.5 amidships.
    tube_station: float = Field(default=0.70, ge=0.35, le=0.92)
    magazine_m3: float = Field(default=76.8, ge=0)
    torpedo_volume_m3: float = Field(default=4.8, gt=0)
    torpedo_mass_t: float = Field(default=2.4, gt=0)
    pdc_mounts: int = Field(default=6, ge=0, le=32)
    pdc_t: float = Field(default=3.5, ge=0)

    @property
    def torpedo_capacity(self) -> int:
        """Everything in the magazine, plus one sitting in each tube."""
        # Decimal dimensions can land one ULP below an integer slot count.
        # Float floor division otherwise turns 105.6 / 4.8 into 21 slots.
        slots = math.floor(math.nextafter(self.magazine_m3 / self.torpedo_volume_m3, math.inf))
        return slots + self.torpedo_tubes

    @property
    def mount_t(self) -> float:
        return (self.railgun_t if self.railgun else 0.0) + self.pdc_mounts * self.pdc_t


class Deck(BaseModel):
    name: str
    kind: DeckKind = DeckKind.CREW
    height_m: float = Field(default=3.0, gt=0, le=12)
    # Only the galley needs interior detail; everything else is a floor plate.
    detailed: bool = False


class CrewMember(BaseModel):
    name: str
    role: str = "crew"
    # Sustained acceleration this person survives, with and without the juice.
    g_tolerance: float = Field(default=5.0, gt=0, le=20)
    juiced_g_tolerance: float = Field(default=12.0, gt=0, le=30)
    mass_kg: float = Field(default=80.0, gt=0)


class ShipSpec(BaseModel):
    """A complete ship. One revision."""

    name: str = "Rocinante"
    hull: Hull = Hull()
    drive: EpsteinDrive = EpsteinDrive()
    weapons: Weapons = Weapons()
    decks: list[Deck] = Field(default_factory=list)
    crew: list[CrewMember] = Field(default_factory=list)
    # Consumables and everything not modelled: stores, water, spares.
    stores_t: float = Field(default=140.0, ge=0)
    # The torpedo this ship carries, as the model rocket OpenRocket flies.
    # Its shape is versioned with the ship; a refit can change it.
    torpedo: RocketSpec = Field(default_factory=baseline_torpedo)

    # Why this revision differs from the last one. Not physics -- this is what
    # a human reads in the review session before approving it.
    rationale: str = ""

    @model_validator(mode="after")
    def _decks_fit_the_hull(self) -> ShipSpec:
        stacked = sum(d.height_m for d in self.decks)
        if stacked > self.hull.length_m:
            raise ValueError(
                f"decks stack to {stacked:.1f} m but the hull is {self.hull.length_m:.1f} m"
            )
        return self

    # --- derived. Never stored; this is what a refit animates. ------------

    @property
    def dry_mass_t(self) -> float:
        crew_t = sum(c.mass_kg for c in self.crew) / 1000.0
        return (
            self.hull.structure_t
            + self.drive.dry_t
            + self.weapons.mount_t
            + self.weapons.torpedo_capacity * self.weapons.torpedo_mass_t
            + self.stores_t
            + crew_t
        )

    @property
    def wet_mass_t(self) -> float:
        return self.dry_mass_t + self.drive.propellant_t

    @property
    def delta_v_km_s(self) -> float:
        """Tsiolkovsky. The one number a refit is judged on."""
        return (
            self.drive.exhaust_velocity_km_s
            * math.log(self.wet_mass_t / self.dry_mass_t)
        )

    @property
    def max_accel_g(self) -> float:
        """Full thrust at full tanks -- the worst case, so it is the honest one."""
        return (self.drive.max_thrust_kn * 1000.0) / (self.wet_mass_t * 1000.0 * G0)

    @property
    def max_burn_hours(self) -> float:
        """Hours at full throttle. Short, and that is the point of a flip."""
        return self.drive.propellant_t * 1000.0 / self.drive.mass_flow_kg_s / 3600.0

    def burn_hours_at(self, accel_g: float) -> float:
        """Hours the tanks last at a given acceleration. Cruise is 1/3 g."""
        thrust_n = accel_g * G0 * self.wet_mass_t * 1000.0
        flow = thrust_n / self.drive.exhaust_velocity_ms
        return self.drive.propellant_t * 1000.0 / flow / 3600.0

    @property
    def sustained_burn_hours(self) -> float:
        """At the 1/3 g cruise the ship actually spends its life at."""
        return self.burn_hours_at(1 / 3)

    @property
    def crew_g_limit(self) -> float:
        """The weakest person on board, juiced. A design bound, not a display."""
        if not self.crew:
            return self.max_accel_g
        return min(c.juiced_g_tolerance for c in self.crew)

    @property
    def crew_limited(self) -> bool:
        """True when the crew, not the drive, is what caps the burn."""
        return self.crew_g_limit < self.max_accel_g

    def derived(self) -> dict[str, float]:
        """The panel under the 3D diff. Order is the order it renders."""
        return {
            "delta_v_km_s": self.delta_v_km_s,
            "dry_mass_t": self.dry_mass_t,
            "wet_mass_t": self.wet_mass_t,
            "torpedo_capacity": float(self.weapons.torpedo_capacity),
            "max_accel_g": self.max_accel_g,
            "crew_g_limit": self.crew_g_limit,
            "sustained_burn_hours": self.sustained_burn_hours,
        }

    def summary(self) -> str:
        return (
            f"dv {self.delta_v_km_s:.0f} km/s | "
            f"dry {self.dry_mass_t:.0f} t | "
            f"torpedoes {self.weapons.torpedo_capacity} | "
            f"max {self.max_accel_g:.1f} g (crew {self.crew_g_limit:.0f} g)"
        )


def json_schema() -> dict:
    """The schema handed to the model as a structured-output contract."""
    return ShipSpec.model_json_schema()
