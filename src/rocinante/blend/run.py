"""Host side of the Blender bridge.

Blender is the mesh generator, not the viewer. It turns a RocketSpec into a
glTF the browser loads. Rendering pixels is reserved for the one hero shot at
the end of the day -- interactive three.js beats a render for a live demo and
costs a fraction of the wall clock.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from rocinante.ship import ShipSpec
from rocinante.spec import RocketSpec

HERE = Path(__file__).parent
BUILD_SCRIPT = HERE / "build_rocket.py"
SHIP_SCRIPT = HERE / "build_ship.py"
LIVE_SHIP_SCRIPT = HERE / "live_ship.py"


class BlenderError(RuntimeError):
    pass


def blender_bin() -> str:
    return os.getenv("BLENDER_BIN", "/Applications/Blender.app/Contents/MacOS/Blender")


def _run(script: Path, payload: dict, timeout: int) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(payload, fh)
        payload_path = fh.name

    cmd = [blender_bin(), "--background", "--factory-startup",
           "--python", str(script), "--", payload_path]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    # Blender can exit 0 after a script raised, so check the output too.
    failed = proc.returncode != 0 or "Traceback (most recent call last)" in proc.stderr
    if failed:
        tail = "\n".join(proc.stdout.splitlines()[-15:])
        raise BlenderError(f"blender exited {proc.returncode}\n{tail}\n{proc.stderr[-1500:]}")
    return proc.stdout


def build_mesh(spec: RocketSpec, out_path: str | Path, timeout: int = 180) -> Path:
    """Build the rocket in Blender and export it as .glb."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        BUILD_SCRIPT,
        {"spec": spec.model_dump(mode="json"), "out": str(out_path.resolve()), "render": None},
        timeout,
    )
    if not out_path.exists():
        raise BlenderError(f"blender ran but produced no file at {out_path}")
    return out_path


def render_still(
    spec: RocketSpec,
    out_path: str | Path,
    resolution: tuple[int, int] = (960, 540),
    timeout: int = 300,
) -> Path:
    """One hero image. EEVEE, low samples. Not for the loop."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        BUILD_SCRIPT,
        {
            "spec": spec.model_dump(mode="json"),
            "out": None,
            "render": {"path": str(out_path.resolve()), "resolution": list(resolution)},
        },
        timeout,
    )
    return out_path


def build_ship_mesh(spec: ShipSpec, out_path: str | Path, timeout: int = 240) -> Path:
    """Regenerate the whole ship from its spec and export it as .glb.

    This is the call beat 4 stands on. It has to be fast enough to run live in
    front of an audience, which is why the hull is generated rather than
    modelled -- see build_ship.py.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        SHIP_SCRIPT,
        {"spec": spec.model_dump(mode="json"), "out": str(out_path.resolve()), "render": None},
        timeout,
    )
    if not out_path.exists():
        raise BlenderError(f"blender ran but produced no ship at {out_path}")
    return out_path


def launch_live_ship(spec_path: str | Path) -> subprocess.Popen:
    """Open Blender's persistent, auto-refreshing Roci scene.

    ``spec_path`` is deliberately a file, rather than an IPC endpoint: it
    keeps the demo inspectable and lets Blender remain a normal editable UI.
    The Blender-side timer regenerates the mesh when its contents change.
    """
    path = Path(spec_path).resolve()
    return subprocess.Popen(
        [blender_bin(), "--factory-startup", "--python", str(LIVE_SHIP_SCRIPT), "--", str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def render_ship_still(
    spec: ShipSpec,
    out_path: str | Path,
    resolution: tuple[int, int] = (1280, 720),
    timeout: int = 420,
) -> Path:
    """The cold-open frame. One render, at the end of the day."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        SHIP_SCRIPT,
        {
            "spec": spec.model_dump(mode="json"),
            "out": None,
            "render": {"path": str(out_path.resolve()), "resolution": list(resolution)},
        },
        timeout,
    )
    return out_path
