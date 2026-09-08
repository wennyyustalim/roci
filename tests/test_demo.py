import json
import zipfile
from xml.etree import ElementTree as ET

from rocinante.demo import latest_torpedo, write_latest_torpedo
from rocinante.ork import write_ork
from rocinante.samples import BASELINE, UNSTABLE


def test_latest_torpedo_falls_back_to_the_sample(tmp_path):
    spec, source = latest_torpedo(tmp_path / "workbench")
    assert spec == BASELINE
    assert "baseline" in source


def test_latest_torpedo_is_the_newest_manifest_iteration(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"iterations": [
        {"index": 1, "spec": BASELINE.model_dump(mode="json")},
        {"index": 2, "spec": UNSTABLE.model_dump(mode="json")},
        {"index": 3, "spec": {"name": "broken"}},
    ]}))
    spec, source = latest_torpedo(tmp_path / "workbench")
    assert spec.name == "Marginal"
    assert source.endswith("v2")


def test_write_latest_torpedo_regenerates_the_file(tmp_path):
    out = tmp_path / "workbench"
    out.mkdir()
    stale = out / "torpedo.ork"
    stale.write_bytes(b"stale")
    path, _ = write_latest_torpedo(out)
    assert path == stale
    assert zipfile.is_zipfile(path)


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
