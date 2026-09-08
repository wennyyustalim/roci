"""Constant-thrust transfers: burn, flip at the midpoint, decelerate in.

The Epstein drive makes the interesting regime the one chemical rockets never
reach -- thrust for the whole trip. That collapses the trajectory problem to
closed form, which is the point: this is real physics, it runs in microseconds,
and a refit's effect on it is exact rather than animated.

    d = a * t_flip^2          each half is a constant-accel leg
    t_total = 2 * sqrt(d / a)
    v_max   = a * t_flip
    dv      = 2 * v_max       accelerate all the way out, brake all the way in
"""

from __future__ import annotations

import math

from pydantic import BaseModel

from rocinante.ship import G0

AU_M = 1.495_978_707e11

# Straight-line distances in AU. Deliberately a table, not an ephemeris: the
# demo needs one honest number per leg, not a solar system simulator. Replace
# with real positions if beat 1 ever gets a date picker.
LEGS: dict[tuple[str, str], float] = {
    ("Tycho", "Ceres"): 0.123,
    ("Ceres", "Mars"): 1.10,
    ("Mars", "Earth"): 0.52,
    ("Earth", "Jupiter"): 4.20,
    ("Ceres", "Ganymede"): 2.55,
    ("Tycho", "Eros"): 0.31,
    ("Ceres", "Ring"): 6.40,
}

# The slow zone clamps everything inside it to this speed. Books, not physics.
RING_SPEED_LIMIT_MS = 18_000.0


class Burn(BaseModel):
    origin: str
    destination: str
    distance_m: float
    accel_g: float

    flip_time_s: float
    total_time_s: float
    peak_velocity_ms: float
    delta_v_km_s: float

    # Set when the ship cannot actually fly this: not enough delta-v, or the
    # crew cannot take the acceleration.
    warnings: list[str] = []

    @property
    def accel_ms2(self) -> float:
        return self.accel_g * G0

    def position_at(self, t: float) -> float:
        """Metres travelled at time t. Drives the track on the system map."""
        t = max(0.0, min(t, self.total_time_s))
        a = self.accel_ms2
        if t <= self.flip_time_s:
            return 0.5 * a * t * t
        remaining = self.total_time_s - t
        return self.distance_m - 0.5 * a * remaining * remaining

    def velocity_at(self, t: float) -> float:
        t = max(0.0, min(t, self.total_time_s))
        a = self.accel_ms2
        if t <= self.flip_time_s:
            return a * t
        return a * (self.total_time_s - t)

    def summary(self) -> str:
        return (
            f"{self.origin} -> {self.destination}   "
            f"{self.accel_g:.2f} g   "
            f"flip at {hms(self.flip_time_s)}   "
            f"arrival {hms(self.total_time_s)}   "
            f"dv {self.delta_v_km_s:.0f} km/s"
        )


def hms(seconds: float) -> str:
    hours, rest = divmod(int(seconds), 3600)
    return f"{hours}h {rest // 60:02d}m"


def distance_between(origin: str, destination: str) -> float:
    """Metres. Legs are symmetric; unknown pairs are an error, not a guess."""
    for (a, b), au in LEGS.items():
        if (a, b) == (origin, destination) or (b, a) == (origin, destination):
            return au * AU_M
    known = ", ".join(sorted({name for leg in LEGS for name in leg}))
    raise KeyError(f"no leg {origin} -> {destination}. Known bodies: {known}")


def solve(
    origin: str,
    destination: str,
    accel_g: float = 1 / 3,
    distance_m: float | None = None,
) -> Burn:
    """The whole flight model. Constant thrust, flip at the midpoint."""
    if accel_g <= 0:
        raise ValueError("acceleration must be positive -- this drive never coasts")
    d = distance_m if distance_m is not None else distance_between(origin, destination)
    a = accel_g * G0

    flip = math.sqrt(d / a)
    return Burn(
        origin=origin,
        destination=destination,
        distance_m=d,
        accel_g=accel_g,
        flip_time_s=flip,
        total_time_s=2 * flip,
        peak_velocity_ms=a * flip,
        delta_v_km_s=2 * a * flip / 1000.0,
    )


def plan(ship, origin: str, destination: str, accel_g: float = 1 / 3) -> Burn:
    """Solve the leg, then check the ship can actually fly it.

    This is the join between beats: the same refit that moved delta_v and
    crew_g_limit decides whether this burn is flyable.
    """
    burn = solve(origin, destination, accel_g)
    warnings: list[str] = []

    if burn.delta_v_km_s > ship.delta_v_km_s:
        short = burn.delta_v_km_s - ship.delta_v_km_s
        warnings.append(
            f"needs {burn.delta_v_km_s:.0f} km/s, ship has {ship.delta_v_km_s:.0f} "
            f"-- {short:.0f} km/s short"
        )
    if accel_g > ship.max_accel_g:
        warnings.append(f"drive tops out at {ship.max_accel_g:.1f} g")
    if accel_g > ship.crew_g_limit:
        warnings.append(f"crew limit is {ship.crew_g_limit:.1f} g -- juice required")
    hours = ship.burn_hours_at(accel_g)
    if burn.total_time_s / 3600.0 > hours:
        warnings.append(f"tanks last {hours:.0f} h, burn is {burn.total_time_s / 3600.0:.0f} h")

    burn.warnings = warnings
    return burn
