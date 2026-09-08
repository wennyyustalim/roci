from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from rocinante.spec import RocketSpec


class SimResult(BaseModel):
    """What one flight tells the agent.

    Keep this backend-neutral. If a field only OpenRocket can produce shows up
    here, the fallback stops being a fallback.
    """

    apogee_m: float
    stability_margin_cal: float
    max_velocity_ms: float = 0.0
    max_acceleration_ms2: float = 0.0
    rail_exit_velocity_ms: float = 0.0
    flight_time_s: float = 0.0
    liftoff_mass_kg: float = 0.0

    # (t, x, y, z) in metres, downsampled. Drives the Blender flight animation.
    trajectory: list[tuple[float, float, float, float]] = Field(default_factory=list)

    warnings: list[str] = Field(default_factory=list)
    backend: str = ""

    def summary(self) -> str:
        return (
            f"apogee {self.apogee_m:.0f} m | "
            f"stability {self.stability_margin_cal:.2f} cal | "
            f"rail exit {self.rail_exit_velocity_ms:.1f} m/s | "
            f"max v {self.max_velocity_ms:.0f} m/s"
        )


@runtime_checkable
class Simulator(Protocol):
    name: str

    def run(self, spec: RocketSpec) -> SimResult:
        """Fly the rocket once. Raise SimulationError if it cannot."""
        ...


class SimulationError(RuntimeError):
    """The design is unflyable, or the backend fell over.

    The agent is allowed to see this message. Make it say something a designer
    could act on.
    """
