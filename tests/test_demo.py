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


def test_open_openrocket_opens_first_then_retires_our_previous_window(monkeypatch, tmp_path):
    calls, scheduled = [], []
    monkeypatch.setattr(demo, "_mac_app_available", lambda name: True)
    monkeypatch.setattr(demo.subprocess, "run", lambda cmd, **kw: calls.append(cmd))
    monkeypatch.setattr(demo, "_close_stale_windows_later", lambda keep: scheduled.append(keep))
    assert demo.open_openrocket(tmp_path / "v0002.ork", "Roci torpedo v2") == "OpenRocket"
    assert calls == [["open", "-a", "OpenRocket", str((tmp_path / "v0002.ork").resolve())]]
    assert scheduled == ["Roci torpedo v2 (v0002.ork)"]


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
