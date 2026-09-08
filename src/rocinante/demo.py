"""The desktop side of `roci demo`: four windows, one screen.

    web UI   | OpenRocket
    ---------+-----------
    Blender  | Kord

Blender watches a spec file and rebuilds itself. OpenRocket has no such hook,
so the workbench writes one `.ork` per revision and opens it; each open lands
a new window on top of the last at the same spot. Kord is a Chrome window the
workbench points at the newest comparison link. Nothing here clicks inside
another app: an earlier attempt to close OpenRocket windows through the
accessibility tree hit a content button instead and wedged the app.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

CHROME_APP = "Google Chrome"
OPENROCKET_APP = "OpenRocket"
MENU_BAR = 33  # points, macOS menu bar; windows cannot sit above it.

Bounds = tuple[int, int, int, int]  # x, y, width, height; origin top-left.


def _osascript(script: str, timeout: float = 15.0) -> str:
    if sys.platform != "darwin":
        return ""
    try:
        done = subprocess.run(["osascript", "-e", script], capture_output=True, text=True,
                              timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip()


def _mac_app_available(name: str) -> bool:
    return sys.platform == "darwin" and (
        Path(f"/Applications/{name}.app").exists()
        or Path(f"~/Applications/{name}.app").expanduser().exists()
    )


# --- layout ---------------------------------------------------------------


def screen_size(default: tuple[int, int] = (1728, 1117)) -> tuple[int, int]:
    """Main display size in points."""
    out = _osascript('tell application "Finder" to get bounds of window of desktop')
    try:
        _, _, width, height = (int(v) for v in out.split(","))
        return width, height
    except ValueError:
        return default


def quadrants(width: int, height: int, menu_bar: int = MENU_BAR) -> dict[str, Bounds]:
    """Split the screen under the menu bar into the four demo windows."""
    half_w, half_h = width // 2, (height - menu_bar) // 2
    top, bottom = menu_bar, menu_bar + half_h
    return {
        "ui": (0, top, half_w, half_h),
        "openrocket": (half_w, top, width - half_w, half_h),
        "blender": (0, bottom, half_w, height - bottom),
        "kord": (half_w, bottom, width - half_w, height - bottom),
    }


def blender_geometry(bounds: Bounds, screen_height: int) -> list[str]:
    """Blender's --window-geometry wants a bottom-left origin."""
    x, y, w, h = bounds
    return ["--window-geometry", str(x), str(screen_height - (y + h)), str(w), str(h)]


def place_window(process: str, title_contains: str, bounds: Bounds, wait_s: float = 60.0) -> None:
    """Move a window of a desktop app into place once it exists. Best effort, in the background."""
    x, y, w, h = bounds
    script = f'''
tell application "System Events"
    if not (exists process "{process}") then return "no process"
    tell process "{process}"
        repeat with win in windows
            if name of win contains "{title_contains}" then
                set position of win to {{{x}, {y}}}
                set size of win to {{{w}, {h}}}
                return "placed"
            end if
        end repeat
    end tell
end tell
return "no window"
'''

    def worker() -> None:
        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline:
            if _osascript(script) == "placed":
                return
            time.sleep(1.0)

    threading.Thread(target=worker, name=f"place-{process}", daemon=True).start()


# --- Chrome -----------------------------------------------------------------


def chrome_open_window(url: str, bounds: Bounds | None = None) -> int | None:
    """Open `url` in its own Chrome window and return the window id, or None without Chrome."""
    if not _mac_app_available(CHROME_APP):
        webbrowser.open(url)
        return None
    set_bounds = ""
    if bounds:
        x, y, w, h = bounds
        set_bounds = f"set bounds of win to {{{x}, {y}, {x + w}, {y + h}}}"
    out = _osascript(f'''
tell application "{CHROME_APP}"
    activate
    set win to make new window
    set URL of active tab of win to "{url}"
    {set_bounds}
    return id of win
end tell
''')
    try:
        return int(out)
    except ValueError:
        return None


def chrome_set_url(window_id: int | None, url: str) -> None:
    """Point an existing Chrome window at `url`; opens a new one if it went away."""
    if window_id is None or not _mac_app_available(CHROME_APP):
        webbrowser.open(url)
        return
    out = _osascript(f'''
tell application "{CHROME_APP}"
    try
        set URL of active tab of window id {window_id} to "{url}"
        return "ok"
    on error
        return "gone"
    end try
end tell
''')
    if out != "ok":
        chrome_open_window(url)


def open_browser(url: str) -> str:
    """Chrome when it is installed, the default browser otherwise."""
    if _mac_app_available(CHROME_APP):
        subprocess.run(["open", "-a", CHROME_APP, url], check=False)
        return CHROME_APP
    webbrowser.open(url)
    return "default browser"


# --- OpenRocket -------------------------------------------------------------


def openrocket_available() -> bool:
    return _mac_app_available(OPENROCKET_APP) or shutil.which("openrocket") is not None


def openrocket_window_title(rocket_name: str, path: Path) -> str:
    return f"{rocket_name} ({Path(path).name})"


def open_openrocket(path: Path, rocket_name: str | None = None,
                    bounds: Bounds | None = None) -> str | None:
    """Show a `.ork` in OpenRocket. Returns how it was opened, or None when it is not installed."""
    resolved = Path(path).resolve()
    if _mac_app_available(OPENROCKET_APP):
        subprocess.run(["open", "-a", OPENROCKET_APP, str(resolved)], check=False)
        if bounds and rocket_name:
            place_window(OPENROCKET_APP, openrocket_window_title(rocket_name, resolved), bounds)
        return OPENROCKET_APP
    if shutil.which("openrocket"):
        subprocess.Popen(
            ["openrocket", str(resolved)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return "openrocket"
    return None
