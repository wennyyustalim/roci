import copy
import importlib.util
import threading
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
    assert result == bench.launch(payload)
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


def test_openrocket_actual_flight():
    if not importlib.util.find_spec("orhelper") or not Path("vendor/OpenRocket-23.09.jar").exists():
        pytest.skip("Requires the optional OpenRocket engine and jar")
    result = OpenRocketSimulator().run(baseline_torpedo())
    assert result.backend == "openrocket"
    assert result.apogee_m > 1
    assert result.max_velocity_ms > 0
    assert result.liftoff_mass_kg > 0
    assert len(result.source_sha256) == 64
    assert len(result.ascent) > 20
    assert all(b[0] > a[0] for a,b in zip(result.ascent, result.ascent[1:]))
    assert max(s[5] for s in result.ascent) > 0
    assert result.ascent[-1][2] == pytest.approx(result.apogee_m, abs=1)
