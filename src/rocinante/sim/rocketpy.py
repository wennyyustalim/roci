"""RocketPy backend. Pure Python, no JVM.

This exists so a JPype problem cannot end the hackathon. It gives a 6-DOF
trajectory that is better than OpenRocket's for the flight animation, and a
static margin that is close enough for the agent to steer on.

    uv pip install -e '.[rocketpy]'
    ROCINANTE_SIM=rocketpy rocinante design "3000 ft, stable"
"""

from __future__ import annotations

from rocinante.sim.base import SimResult, SimulationError
from rocinante.spec import RocketSpec


class RocketPySimulator:
    name = "rocketpy"

    def run(self, spec: RocketSpec) -> SimResult:
        try:
            from rocketpy import Environment, Flight, Rocket, SolidMotor  # noqa: F401
        except ImportError as exc:
            raise SimulationError(
                "rocketpy is not installed. `uv pip install -e '.[rocketpy]'`"
            ) from exc

        # TODO: build Environment -> SolidMotor -> Rocket from `spec`, then Flight.
        # RocketPy needs a thrust curve file; keep two or three .eng files in
        # vendor/motors/ and map spec.motor.designation onto them.
        raise NotImplementedError("map RocketSpec onto RocketPy objects")
