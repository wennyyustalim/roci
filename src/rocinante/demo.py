"""The desktop side of `roci demo`: four windows, one screen.

    web UI   | OpenRocket
    ---------+-----------
    Blender  | Kord

Blender watches the ship spec and selection files in its persistent session.
The document bridge in openrocket_live.py updates OpenRocket's existing
workshop document on Swing's event thread. This module opens the application
only when needed and handles its initial layout. Kord's Chrome window follows
the newest comparison link.

OPENROCKET IS NOT PLACED THROUGH SYSTEM EVENTS, and cannot be. It is a Swing
app, and Swing publishes no windows to the macOS accessibility API: with the
torpedo plainly on screen, `count of windows` of its process is 0, so there is
nothing for AppleScript to move. Its process is not called "OpenRocket"
either -- the install4j bundle runs as `JavaApplicationStub`, so even
`exists process "OpenRocket"` is false. What OpenRocket does do is save its
main frame's geometry in the Java preferences plist and restore it on launch.
`prepare_openrocket()` writes the quadrant there before the app starts; see
its docstring for why the app has to be quit for that to take.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

CHROME_APP = "Google Chrome"
OPENROCKET_APP = "OpenRocket"
MENU_BAR = 33  # points, macOS menu bar; windows cannot sit above it.

# Where Java's Preferences API keeps this user's settings, and the node
# OpenRocket restores its main window from.
JAVA_PREFS = Path("~/Library/Preferences/com.apple.java.util.prefs.plist").expanduser()
OPENROCKET_WINDOWS = ":/:OpenRocket/:windows/"
OPENROCKET_FRAME = "info.openrocket.swing.gui.main.BasicFrame"

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


def process_name(app: str) -> str:
    """The name System Events knows `app` by, or "" when it is not running.

    System Events keys processes by executable name, which is not always the
    app's own: OpenRocket runs as `JavaApplicationStub`. Look it up by the
    displayed name instead of assuming they match.
    """
    return _osascript(
        'tell application "System Events" to get name of first process '
        f'whose displayed name is "{app}"'
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


class KordWindow:
    """The Chrome window showing the comparison, kept on the newest revision.

    A revision's Kord link is minted after the model has answered and the
    export has run, so it can arrive late -- and when the next ask took the
    workbench lock while this one waited on it, it can arrive *after* a newer
    link. Carrying the revision index is what lets the window ignore that one
    instead of stepping back a revision behind the workbench.
    """

    def __init__(self, window_id: int | None = None, showing: int = -1) -> None:
        self.window_id = window_id
        self.showing = showing

    def open(self, url: str, index: int = -1, bounds: Bounds | None = None) -> None:
        self.window_id = chrome_open_window(url, bounds)
        self.showing = index

    def show(self, url: str, index: int) -> bool:
        """Navigate to a revision's comparison. False when it is already behind."""
        if index <= self.showing:
            return False
        self.showing = index
        chrome_set_url(self.window_id, url)
        return True


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


def openrocket_running() -> bool:
    return bool(process_name(OPENROCKET_APP))


def openrocket_window_title(rocket_name: str, path: Path) -> str:
    return f"{rocket_name} ({Path(path).name})"


def _plist_write(entry: str, value: str, path: Path = JAVA_PREFS) -> bool:
    """Set one string entry, creating it when the node is new. True when it took."""
    for command in (f"Set {entry} {value}", f"Add {entry} string {value}"):
        done = subprocess.run(["/usr/libexec/PlistBuddy", "-c", command, str(path)],
                              capture_output=True, text=True, check=False)
        if done.returncode == 0:
            return True
    return False


def seed_openrocket_bounds(bounds: Bounds, path: Path = JAVA_PREFS) -> bool:
    """Write the geometry OpenRocket restores its main window from.

    This is the only lever we have on where that window lands (see the module
    docstring), and it is read at launch, so it must be written while the app
    is not running -- OpenRocket owns the file in between and writes its own
    values back on exit.
    """
    if sys.platform != "darwin":
        return False
    x, y, w, h = bounds
    for node in (":/", ":/:OpenRocket/", OPENROCKET_WINDOWS):
        subprocess.run(["/usr/libexec/PlistBuddy", "-c", f"Add {node} dict", str(path)],
                       capture_output=True, text=True, check=False)  # no-op when present
    return all(
        _plist_write(f"{OPENROCKET_WINDOWS}:{key}.{OPENROCKET_FRAME}", value, path)
        for key, value in (("position", f"{x},{y}"), ("size", f"{w},{h}"))
    )


def quit_openrocket(wait_s: float = 12.0) -> bool:
    """Ask OpenRocket to quit and wait for it to go. False if it is still up.

    It stays up when it has an unsaved design and puts a save prompt on screen.
    That is a person's decision, so the caller carries on without it rather
    than forcing anything.
    """
    if not openrocket_running():
        return True
    _osascript(f'quit app "{OPENROCKET_APP}"')
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        if not openrocket_running():
            return True
        time.sleep(0.5)
    return False


def prepare_openrocket(bounds: Bounds | None) -> bool:
    """Get OpenRocket ready to open the torpedo in its quadrant. True when it will land there.

    Restarting it is what makes the seeded geometry take, and it also clears
    the stack of windows every previous revision left behind.
    """
    if bounds is None or not _mac_app_available(OPENROCKET_APP):
        return False
    return quit_openrocket() and seed_openrocket_bounds(bounds)


def open_openrocket(path: Path, rocket_name: str | None = None,
                    bounds: Bounds | None = None) -> str | None:
    """Show a `.ork` in OpenRocket. Returns how it was opened, or None when it is not installed."""
    resolved = Path(path).resolve()
    if _mac_app_available(OPENROCKET_APP):
        if bounds and not openrocket_running():
            seed_openrocket_bounds(bounds)
        subprocess.run(["open", "-a", OPENROCKET_APP, str(resolved)], check=False)
        return OPENROCKET_APP
    if shutil.which("openrocket"):
        subprocess.Popen(
            ["openrocket", str(resolved)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return "openrocket"
    return None
