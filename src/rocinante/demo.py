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
        if rocket_name:
            close_stale_openrocket_windows(openrocket_window_title(rocket_name, resolved))
        subprocess.run(["open", "-a", OPENROCKET_APP, str(resolved)], check=False)
        return OPENROCKET_APP
    if shutil.which("openrocket"):
        subprocess.Popen(
            ["openrocket", str(resolved)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return "openrocket"
    return None


def close_stale_openrocket_windows(keep_title: str) -> None:
    """Close our older torpedo windows. Needs Accessibility access; silently skipped without."""
    if sys.platform != "darwin":
        return
    script = _CLOSE_STALE_WINDOWS.format(app=OPENROCKET_APP, keep=keep_title)
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        pass
