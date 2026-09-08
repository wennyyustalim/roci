"""Everything `roci demo` opens besides the workbench server.

Three windows tell the story: Chrome for the review UI, Blender for the ship,
OpenRocket for the torpedo. The workbench already drives the Blender window;
this module finds the newest torpedo, writes it as a fresh `.ork`, and opens
the desktop apps. Kept free of the HTTP server so it is testable on its own.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

from rocinante.ork import write_ork
from rocinante.samples import BASELINE
from rocinante.spec import RocketSpec

CHROME_APP = "Google Chrome"
OPENROCKET_APP = "OpenRocket"
OPENROCKET_APP_PATH = Path("/Applications/OpenRocket.app")


def latest_torpedo(out: Path) -> tuple[RocketSpec, str]:
    """The newest torpedo design, and where it came from.

    `rocinante design` writes a manifest with every iteration's spec. Look in
    the demo directory first, then its parent (the loop's default `out/`).
    With no run on disk, the sample baseline torpedo is the latest design.
    """
    for directory in (out, out.parent):
        manifest = directory / "manifest.json"
        if not manifest.is_file():
            continue
        try:
            iterations = json.loads(manifest.read_text()).get("iterations", [])
        except (OSError, json.JSONDecodeError):
            continue
        for iteration in reversed(iterations):
            spec = iteration.get("spec")
            if not spec:
                continue
            try:
                return RocketSpec.model_validate(spec), f"{manifest} v{iteration.get('index', '?')}"
            except ValueError:
                continue
    return BASELINE, "sample baseline (no design run found)"


def write_latest_torpedo(out: Path) -> tuple[Path, str]:
    """Always regenerate: a stale `.ork` on disk may predate the writer's format."""
    spec, source = latest_torpedo(out)
    return write_ork(spec, out / "torpedo.ork"), source


def _mac_app_available(name: str) -> bool:
    return sys.platform == "darwin" and (
        Path(f"/Applications/{name}.app").exists() or Path(f"~/Applications/{name}.app").expanduser().exists()
    )


def open_browser(url: str) -> str:
    """Chrome when it is installed, the default browser otherwise."""
    if _mac_app_available(CHROME_APP):
        subprocess.run(["open", "-a", CHROME_APP, url], check=False)
        return CHROME_APP
    webbrowser.open(url)
    return "default browser"


def open_openrocket(path: Path) -> str | None:
    """Open a `.ork` in the OpenRocket desktop app. Returns how, or None if absent."""
    resolved = str(Path(path).resolve())
    if _mac_app_available(OPENROCKET_APP):
        subprocess.run(["open", "-a", OPENROCKET_APP, resolved], check=False)
        return OPENROCKET_APP
    if shutil.which("openrocket"):
        subprocess.Popen(["openrocket", resolved], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "openrocket"
    return None
