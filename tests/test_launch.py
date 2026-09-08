import copy
import importlib.util
import json
import threading
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import httpx
import pytest

from rocinante.sim.base import SimResult, SimulationError
from rocinante.sim.openrocket import OpenRocketSimulator
from rocinante.spec import baseline_torpedo
from rocinante.workbench import Workbench, make_server


def test_launch_uses_accepted_instance_and_caches_without_consuming_it(tmp_path, monkeypatch):
    bench = Workbench(tmp_path, auto_accept=True)
    bench.propose({"preset": "nose", "torpedo_id": "torpedo_02"})
    before = copy.deepcopy(bench.state)
    calls = []
    def run(self, spec):
        calls.append(spec)
        return SimResult(apogee_m=30, stability_margin_cal=1,
                         ascent=[[0,0,0,0,0,0], [2,0,30,0,20,0]], backend="openrocket")
    monkeypatch.setattr(OpenRocketSimulator, "run", run)
    payload = {"torpedo_id": "torpedo_02", "index": 1}
    result = bench.launch(payload)
    replay = bench.launch(payload)
    assert result["simulation"] == replay["simulation"]
    assert result["launch_id"] != replay["launch_id"]
    assert len(calls) == 1
    assert calls[0].nose.length_m == pytest.approx(before["iterations"][1]["torpedoes"]["torpedo_02"]["nose"]["length_m"])
    assert bench.state == before
    for invalid in ({"index":1}, {"index":1,"torpedo_id":"../bad"}, {"index":0,"torpedo_id":"torpedo_02"}):
        with pytest.raises(ValueError):
            bench.launch(invalid)
    bench.launch({"torpedo_id":"torpedo_01", "index":1})
    assert len(calls) == 2


def test_launch_http_engine_failure_and_assets(tmp_path, monkeypatch):
    bench = Workbench(tmp_path)
    def fail(self, spec):
        raise SimulationError("Motor not found")
    monkeypatch.setattr(OpenRocketSimulator, "run", fail)
    server = make_server(bench, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_port}") as client:
            for asset in ("/launch.js", "/torpedo.js"):
                assert client.get(asset).status_code == 200
            response = client.post("/api/launch", json={"torpedo_id":"torpedo_01", "index":0})
            assert response.status_code == 422
            assert response.json() == {"error":"Motor not found"}
            assert bench.state["accepted"] == 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_openrocket_actual_flight(tmp_path):
    if not importlib.util.find_spec("orhelper") or not Path("vendor/OpenRocket-23.09.jar").exists():
        pytest.skip("Requires the optional OpenRocket engine and jar")
    flight = tmp_path / "flight.ork"
    result = OpenRocketSimulator(flight_path=flight).run(baseline_torpedo())
    xml = ET.fromstring(zipfile.ZipFile(flight).read("rocket.ork"))
    simulation = xml.find("simulations/simulation")
    assert simulation is not None
    assert len(simulation.findall("flightdata/databranch/datapoint")) >= len(result.ascent)
    assert float(simulation.find("flightdata").attrib["maxaltitude"]) == pytest.approx(result.apogee_m, abs=.001)
    assert result.backend == "openrocket"
    assert result.apogee_m > 1
    assert result.max_velocity_ms > 0
    assert result.liftoff_mass_kg > 0
    assert len(result.source_sha256) == 64
    assert len(result.ascent) > 20
    assert all(b[0] > a[0] for a,b in zip(result.ascent, result.ascent[1:]))
    assert max(s[5] for s in result.ascent) > 0
    assert result.ascent[-1][2] == pytest.approx(result.apogee_m, abs=1)


def test_desktop_playback_orders_clock_and_rejects_stale_runs(tmp_path, monkeypatch):
    bench = Workbench(tmp_path)
    monkeypatch.setattr(OpenRocketSimulator, "run", lambda self, spec:
        SimResult(apogee_m=30, stability_margin_cal=1, ascent=[[0,0,0,0,0,0],[2,0,30,0,20,0]]))
    run = bench.launch({"torpedo_id":"torpedo_01", "index":0})
    sample = {"launch_id":run["launch_id"], "time":1.5, "sequence":2, "phase":"flight"}
    bench.launch_playback(sample)
    clock = tmp_path / "openrocket-playback.properties"
    assert "time=1.5" in clock.read_text()
    bench.launch_playback({**sample,"time":.5,"sequence":1})
    assert "time=1.5" in clock.read_text()
    for invalid in ({"time":float("nan")}, {"time":-1}, {"time":20}, {"sequence":"3"}, {"phase":"bad"}):
        with pytest.raises(ValueError):
            bench.launch_playback({**sample, **invalid})
    (tmp_path / "openrocket-selection-status.json").write_text(json.dumps({"request_id":int(run["launch_id"]), "status":"synced"}))
    assert bench.launch_playback({**sample,"phase":"complete","sequence":3})["status"] == "synced"
    bench.launch({"torpedo_id":"torpedo_02", "index":0})
    with pytest.raises(ValueError, match="no longer active"):
        bench.launch_playback(sample)


def test_launch_opens_exact_saved_flight_on_every_replay(tmp_path, monkeypatch):
    bench = Workbench(tmp_path)
    bench.show_openrocket = True
    def simulate(self, spec):
        self.flight_path.parent.mkdir(parents=True, exist_ok=True)
        self.flight_path.write_bytes(b"saved flight")
        return SimResult(apogee_m=30, stability_margin_cal=1, ascent=[[0,0,0,0,0,0],[2,0,30,0,20,0]])
    monkeypatch.setattr(OpenRocketSimulator, "run", simulate)
    calls = []
    def show(path, selection, bounds, *, simulation):
        calls.append((path,simulation))
        return {"status":"pending"}
    monkeypatch.setattr("rocinante.openrocket_live.show_in_openrocket", show)
    first = bench.launch({"torpedo_id":"torpedo_01", "index":0})
    second = bench.launch({"torpedo_id":"torpedo_01", "index":0})
    assert len(calls) == 2
    assert calls[0][0] == calls[1][0]
    assert calls[0][0].read_bytes() == b"saved flight"
    assert calls[0][1]["request_id"] == first["launch_id"]
    assert calls[1][1]["request_id"] == second["launch_id"]
