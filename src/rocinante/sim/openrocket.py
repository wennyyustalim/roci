"""Run OpenRocket 23.09 in an isolated worker so its JVM never owns the UI process."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from rocinante.ork import write_ork
from rocinante.sim.base import SimResult, SimulationError
from rocinante.spec import RocketSpec


class OpenRocketSimulator:
    name = "openrocket"

    def __init__(self, jar: str | None = None, flight_path: Path | None = None) -> None:
        self.flight_path = flight_path
        default = Path(__file__).resolve().parents[3] / "vendor/OpenRocket-23.09.jar"
        self.jar = Path(jar or os.getenv("OPENROCKET_JAR", str(default))).resolve()

    def run(self, spec: RocketSpec) -> SimResult:
        if not self.jar.is_file():
            raise SimulationError(f"OpenRocket jar not found at {self.jar}")
        with tempfile.TemporaryDirectory(prefix="rocinante-flight-") as directory:
            folder = Path(directory)
            source = write_ork(spec, folder / "torpedo.ork")
            result = folder / "result.json"
            env = dict(os.environ)
            env["JAVA_TOOL_OPTIONS"] = env.get("JAVA_TOOL_OPTIONS", "") + " -Djava.awt.headless=true"
            if "JAVA_HOME" not in env:
                jdk = Path("/opt/homebrew/opt/openjdk/libexec/openjdk.jdk/Contents/Home")
                if jdk.is_dir():
                    env["JAVA_HOME"] = str(jdk)
            try:
                process = subprocess.run(
                    [sys.executable, "-m", "rocinante.sim.openrocket", str(self.jar),
                     str(source), str(result)], env=env, capture_output=True, text=True, timeout=45, check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise SimulationError("OpenRocket timed out. Try launching again.") from exc
            if process.returncode or not result.exists():
                if "No module named 'orhelper'" in process.stderr:
                    raise SimulationError("Install the flight engine with uv sync --extra openrocket.")
                raise SimulationError("OpenRocket could not fly this design. Check its motor and geometry.")
            if self.flight_path is not None:
                self.flight_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(result.with_suffix(".ork"), self.flight_path)
            return SimResult.model_validate_json(result.read_text())

    def close(self) -> None:
        pass  # Each worker shuts its own JVM down.


def _worker(jar: str, source: str, destination: str):
    import math

    import jpype
    import orhelper

    with orhelper.OpenRocketInstance(jar) as instance:
        helper = orhelper.Helper(instance)
        document = helper.load_doc(source)
        rocket = document.getRocket()
        sim = instance.openrocket.document.Simulation(document, rocket)
        sim.setFlightConfigurationId(rocket.getSelectedConfiguration().getFlightConfigurationID())
        options = sim.getOptions()
        options.setWindSpeedAverage(0)
        options.setWindTurbulenceIntensity(0)
        options.setLaunchRodAngle(0)
        options.setLaunchRodLength(1)
        options.setTimeStep(.025)
        options.setRandomSeed(7)
        listeners = jpype.JArray(instance.openrocket.simulation.listeners.AbstractSimulationListener)(0)
        sim.simulate(listeners)
        flight = sim.getSimulatedData()
        branch = flight.getBranch(0)
        types = instance.openrocket.simulation.FlightDataType
        def values(name):
            return [float(n) for n in branch.get(getattr(types, "TYPE_" + name))]
        times, xs, ys, zs = [values(n) for n in ("TIME", "POSITION_X", "POSITION_Y", "ALTITUDE")]
        speeds, thrust = values("VELOCITY_TOTAL"), values("THRUST_FORCE")
        # Keep the full flight in the neutral result; the training scene uses ascent only.
        finite = lambda x: x if math.isfinite(x) else 0.0
        indices = sorted(set(range(0, len(times), max(1, len(times)//500))) | {len(times)-1})
        trajectory = [(times[i], xs[i], ys[i], zs[i]) for i in indices
                      if all(math.isfinite(n) for n in (times[i], xs[i], ys[i], zs[i]))]
        samples = [[times[i], xs[i], zs[i], -ys[i], finite(speeds[i]), finite(thrust[i])]
                   for i in range(len(times)) if times[i] <= flight.getTimeToApogee()
                   and all(math.isfinite(n) for n in (times[i], xs[i], ys[i], zs[i]))]
        if len(samples) < 2 or samples[-1][0] <= 0 or flight.getMaxAltitude() < 1:
            raise SimulationError("This design did not produce a usable ascent.")
        result = SimResult(
            apogee_m=finite(flight.getMaxAltitude()), max_velocity_ms=finite(flight.getMaxVelocity()),
            max_acceleration_ms2=finite(flight.getMaxAcceleration()),
            rail_exit_velocity_ms=finite(flight.getLaunchRodVelocity()),
            flight_time_s=finite(flight.getFlightTime()), liftoff_mass_kg=finite(values("MASS")[0]),
            stability_margin_cal=finite(values("STABILITY")[0]), trajectory=trajectory,
            warnings=[str(w) for w in flight.getWarningSet()], backend="openrocket",
            ascent=samples, source_sha256=hashlib.sha256(Path(source).read_bytes()).hexdigest(),
        )
        # Persist the same simulated document, including every flight sample, for
        # the desktop plot. Never ask the desktop engine to recompute another flight.
        import zipfile
        sim.setName("Rocinante launch · OpenRocket 23.09")
        document.addSimulation(sim)
        storage = instance.openrocket.document.StorageOptions()
        storage.setSaveSimulationData(True)
        stream = jpype.java.io.ByteArrayOutputStream()
        instance.openrocket.file.openrocket.OpenRocketSaver().save(
            stream, document, storage, instance.openrocket.logging.WarningSet(),
            instance.openrocket.logging.ErrorSet(),
        )
        with zipfile.ZipFile(Path(destination).with_suffix(".ork"), "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("rocket.ork", bytes(stream.toByteArray()))
        Path(destination).write_text(result.model_dump_json())


if __name__ == "__main__":
    _worker(*sys.argv[1:])
