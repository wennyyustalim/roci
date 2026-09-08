import subprocess
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from rocinante import demo
from rocinante.ork import write_ork
from rocinante.samples import BASELINE


def test_openrocket_window_title_matches_the_app_convention():
    assert demo.openrocket_window_title("Rocinante torpedo v3", Path("/x/v0003.ork")) == (
        "Rocinante torpedo v3 (v0003.ork)"
    )


def test_open_openrocket_reports_absence_instead_of_raising(monkeypatch, tmp_path):
    monkeypatch.setattr(demo, "_mac_app_available", lambda name: False)
    monkeypatch.setattr(demo.shutil, "which", lambda name: None)
    assert demo.open_openrocket(tmp_path / "t.ork", "Torpedo v1") is None


def test_open_openrocket_opens_the_file_and_seeds_the_window_geometry(monkeypatch, tmp_path):
    calls, seeded = [], []
    monkeypatch.setattr(demo, "_mac_app_available", lambda name: True)
    monkeypatch.setattr(demo, "openrocket_running", lambda: False)
    monkeypatch.setattr(demo.subprocess, "run", lambda cmd, **kw: calls.append(cmd))
    monkeypatch.setattr(demo, "seed_openrocket_bounds", lambda b: seeded.append(b))
    bounds = (864, 33, 864, 542)
    assert demo.open_openrocket(tmp_path / "v0002.ork", "Roci torpedo v2", bounds) == "OpenRocket"
    assert calls == [["open", "-a", "OpenRocket", str((tmp_path / "v0002.ork").resolve())]]
    assert seeded == [bounds]


def test_open_openrocket_leaves_geometry_alone_while_the_app_is_running(monkeypatch, tmp_path):
    """A running OpenRocket owns the prefs file and writes its own values back on exit."""
    seeded = []
    monkeypatch.setattr(demo, "_mac_app_available", lambda name: True)
    monkeypatch.setattr(demo, "openrocket_running", lambda: True)
    monkeypatch.setattr(demo.subprocess, "run", lambda cmd, **kw: None)
    monkeypatch.setattr(demo, "seed_openrocket_bounds", lambda b: seeded.append(b))
    demo.open_openrocket(tmp_path / "v0003.ork", "Roci torpedo v3", (864, 33, 864, 542))
    assert seeded == []


def test_seed_openrocket_bounds_writes_the_node_openrocket_restores_from(tmp_path):
    prefs = tmp_path / "com.apple.java.util.prefs.plist"
    assert demo.seed_openrocket_bounds((864, 33, 864, 542), prefs)

    def read(entry: str) -> str:
        return subprocess.run(["/usr/libexec/PlistBuddy", "-c", f"Print {entry}", str(prefs)],
                              capture_output=True, text=True, check=True).stdout.strip()

    frame = f"{demo.OPENROCKET_WINDOWS}:%s.{demo.OPENROCKET_FRAME}"
    assert read(frame % "position") == "864,33"
    assert read(frame % "size") == "864,542"
    # Written again over an existing node, not duplicated beside it.
    assert demo.seed_openrocket_bounds((0, 33, 700, 400), prefs)
    assert read(frame % "position") == "0,33"
    assert read(frame % "size") == "700,400"


def test_kord_window_ignores_a_link_that_arrives_after_a_newer_one(monkeypatch):
    """A slow upload must not step the window back behind the workbench."""
    went = []
    monkeypatch.setattr(demo, "chrome_set_url", lambda window_id, url: went.append(url))
    window = demo.KordWindow(window_id=7)

    assert window.show("/d/one", 1)
    assert window.show("/d/three", 3)
    assert not window.show("/d/two", 2)  # v2 finished uploading after v3
    assert not window.show("/d/three-again", 3)  # a repeated share of the same revision
    assert went == ["/d/one", "/d/three"]


def test_kord_window_starts_on_the_revision_its_saved_link_belongs_to(monkeypatch):
    monkeypatch.setattr(demo, "chrome_open_window", lambda url, bounds: 11)
    monkeypatch.setattr(demo, "chrome_set_url", lambda window_id, url: None)
    window = demo.KordWindow()
    window.open("/d/saved", 4, (864, 575, 864, 542))
    assert (window.window_id, window.showing) == (11, 4)
    # A restart must not replay revisions the saved link already covers.
    assert not window.show("/d/older", 3)
    assert window.show("/d/newer", 5)


def test_quadrants_tile_the_screen_under_the_menu_bar():
    quads = demo.quadrants(1728, 1117)
    assert quads["ui"] == (0, 33, 864, 542)
    assert quads["openrocket"] == (864, 33, 864, 542)
    assert quads["blender"] == (0, 575, 864, 542)
    assert quads["kord"] == (864, 575, 864, 542)
    # Blender counts y from the bottom of the screen.
    assert demo.blender_geometry(quads["blender"], 1117) == ["--window-geometry", "0", "0", "864", "542"]


def test_ork_uses_openrocket_position_and_motor_mount_elements(tmp_path):
    with zipfile.ZipFile(write_ork(BASELINE, tmp_path / "r.ork")) as zf:
        root = ET.fromstring(zf.read("rocket.ork"))
    assert root.find("rocket/subcomponents/stage/name").text == "Sustainer"
    fins = root.find(".//trapezoidfinset")
    assert fins.find("axialoffset").get("method") == "bottom"
    assert fins.find("axialmethod") is None
    mount = root.find(".//innertube/motormount")
    assert mount.find("motor/designation").text == BASELINE.motor.designation
    config_id = mount.find("motor").get("configid")
    assert root.find("rocket/motorconfiguration").get("configid") == config_id
    assert root.find(".//parachute/deployevent").text == "apogee"
