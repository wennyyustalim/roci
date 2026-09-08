"""OpenRocket backend, driven headlessly through orhelper (JPype -> the jar).

STATUS: skeleton.

TIMEBOX THIS TO ONE HOUR ON THE DAY. If the JVM bridge is still fighting you
at 11am, set ROCINANTE_SIM=rocketpy and move on -- the rest of the project does
not care which backend produced the numbers.

Setup:
    brew install --cask temurin
    mkdir -p vendor && curl -L -o vendor/OpenRocket-23.09.jar \
      https://github.com/openrocket/openrocket/releases/download/release-23.09/OpenRocket-23.09.jar
    uv pip install -e '.[openrocket]'
"""

from __future__ import annotations

import os
from pathlib import Path

from rocinante.ork import write_ork
from rocinante.sim.base import SimResult, SimulationError
from rocinante.spec import RocketSpec


class OpenRocketSimulator:
    name = "openrocket"

    def __init__(self, jar: str | None = None) -> None:
        self.jar = Path(jar or os.getenv("OPENROCKET_JAR", "vendor/OpenRocket-23.09.jar"))
        self._instance = None

    def _orhelper(self):
        """Start the JVM once and keep it. Booting it per flight is far too slow."""
        if self._instance is None:
            try:
                import orhelper
            except ImportError as exc:  # pragma: no cover
                raise SimulationError(
                    "orhelper is not installed. `uv pip install -e '.[openrocket]'`, "
                    "or set ROCINANTE_SIM=rocketpy."
                ) from exc
            if not self.jar.exists():
                raise SimulationError(f"OpenRocket jar not found at {self.jar}")
            self._instance = orhelper.OpenRocketInstance(str(self.jar))
            self._instance.__enter__()
        return self._instance

    def run(self, spec: RocketSpec) -> SimResult:
        import orhelper
        from orhelper import FlightDataType

        instance = self._orhelper()
        helper = orhelper.Helper(instance)

        ork_path = write_ork(spec, Path("out/sim") / f"{abs(hash(spec.model_dump_json()))}.ork")
        doc = helper.load_doc(str(ork_path))
        sim = doc.getSimulation(0)
        helper.run_simulation(sim)

        data = helper.get_timeseries(  # noqa: F841
            sim,
            [
                FlightDataType.TYPE_TIME,
                FlightDataType.TYPE_ALTITUDE,
                FlightDataType.TYPE_POSITION_X,
                FlightDataType.TYPE_POSITION_Y,
                FlightDataType.TYPE_VELOCITY_TOTAL,
                FlightDataType.TYPE_STABILITY,
            ],
        )
        events = helper.get_events(sim)  # noqa: F841  # TODO: rail exit, apogee, deploy

        # TODO: map `data` onto SimResult. Downsample the trajectory to ~200
        # points before it goes anywhere near Blender or the browser.
        raise NotImplementedError("wire orhelper timeseries into SimResult")

    def close(self) -> None:
        if self._instance is not None:
            self._instance.__exit__(None, None, None)
            self._instance = None
