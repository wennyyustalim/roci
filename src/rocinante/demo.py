"""The desktop apps `roci demo` opens beside the workbench server.

Three windows tell the story: Chrome for the review UI, Blender for the ship,
OpenRocket for the torpedo. Blender watches a spec file and rebuilds itself.
OpenRocket has no such hook, so the workbench writes one `.ork` per revision
and reopens it; the previous torpedo window is closed as a best effort so the
newest design is the one on screen. Kept free of the HTTP server so it is
testable on its own.
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

# Title of an OpenRocket window we opened: "<rocket name> (<file name>)".
_CLOSE_STALE_WINDOWS = '''
tell application "System Events"
    if not (exists process "{app}") then return
    tell process "{app}"
        repeat with w in windows
            set t to name of w
            if t ends with ".ork)" and t is not "{keep}" then
                try
                    click button 1 of w
                end try
            end if
        end repeat
    end tell
end tell
'''


def _mac_app_available(name: str) -> bool:
    return sys.platform == "darwin" and (
        Path(f"/Applications/{name}.app").exists()
        or Path(f"~/Applications/{name}.app").expanduser().exists()
    )


def open_browser(url: str) -> str:
    """Chrome when it is installed, the default browser otherwise."""
    if _mac_app_available(CHROME_APP):
        subprocess.run(["open", "-a", CHROME_APP, url], check=False)
        return CHROME_APP
    webbrowser.open(url)
    return "default browser"


def openrocket_available() -> bool:
    return _mac_app_available(OPENROCKET_APP) or shutil.which("openrocket") is not None


def openrocket_window_title(rocket_name: str, path: Path) -> str:
    return f"{rocket_name} ({Path(path).name})"


def open_openrocket(path: Path, rocket_name: str | None = None) -> str | None:
    """Show a `.ork` in OpenRocket, replacing the torpedo window we opened before.

    Returns how it was opened, or None when OpenRocket is not installed.
    """
    resolved = Path(path).resolve()
    if _mac_app_available(OPENROCKET_APP):
        subprocess.run(["open", "-a", OPENROCKET_APP, str(resolved)], check=False)
        if rocket_name:
            # Close the old window only after the new one exists: closing the
            # last document window makes OpenRocket quit on us.
            _close_stale_windows_later(openrocket_window_title(rocket_name, resolved))
        return OPENROCKET_APP
    if shutil.which("openrocket"):
        subprocess.Popen(
            ["openrocket", str(resolved)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return "openrocket"
    return None


_WINDOW_TITLES = '''
tell application "System Events"
    if not (exists process "{app}") then return ""
    tell process "{app}" to return name of windows as string
end tell
'''


def _close_stale_windows_later(keep_title: str, wait_s: float = 45.0) -> threading.Thread:
    def worker() -> None:
        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline:
            try:
                titles = subprocess.run(
                    ["osascript", "-e", _WINDOW_TITLES.format(app=OPENROCKET_APP)],
                    capture_output=True, text=True, timeout=10, check=False,
                ).stdout
            except (OSError, subprocess.SubprocessError):
                return
            if keep_title in titles:
                close_stale_openrocket_windows(keep_title)
                return
            time.sleep(1.0)

    thread = threading.Thread(target=worker, name="openrocket-windows", daemon=True)
    thread.start()
    return thread


def close_stale_openrocket_windows(keep_title: str) -> None:
    """Close our older torpedo windows. Needs Accessibility access; silently skipped without."""
    if sys.platform != "darwin":
        return
    script = _CLOSE_STALE_WINDOWS.format(app=OPENROCKET_APP, keep=keep_title)
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        pass
