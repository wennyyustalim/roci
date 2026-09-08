import threading

import httpx
import pytest

from rocinante.samples import ROCINANTE
from rocinante.workbench import Workbench, make_server


def test_propose_review_repeat_and_reload(tmp_path):
    bench = Workbench(tmp_path)
    first = bench.propose({"preset": "torpedoes"})["iterations"][-1]
    assert first["status"] == "pending"
    assert first["derived"]["torpedo_capacity"] == ROCINANTE.weapons.torpedo_capacity + 8
    assert first["derived"]["sustained_burn_hours"] == pytest.approx(
        ROCINANTE.sustained_burn_hours
    )
    assert "tube_*" in first["changed_parts"]
    assert bench.state["accepted"] == 0
    with pytest.raises(ValueError, match="pending"):
        bench.propose({"preset": "armor"})
    bench.decide({"index": 1, "verdict": "approved"})
    bench = Workbench(tmp_path)
    second = bench.propose({"preset": "armor"})["iterations"][-1]
    assert second["parent"] == 1
    assert second["derived"]["delta_v_km_s"] < first["derived"]["delta_v_km_s"]
    assert second["mission"]["total_time_s"] == first["mission"]["total_time_s"]
    bench.decide({"index": 2, "verdict": "rejected"})
    third = bench.propose({"preset": "drive"})["iterations"][-1]
    assert third["parent"] == 1
    assert third["spec"]["hull"]["armor_cm"] == ROCINANTE.hull.armor_cm
    assert third["derived"] == first["derived"]
    assert third["changed_parts"] == ["drive_*"]


def test_bad_requests_leave_design_unchanged(tmp_path):
    bench = Workbench(tmp_path)
    with pytest.raises(ValueError):
        bench.propose({"preset": "invented"})
    bench.propose({"preset": "drive"})
    for payload in [{"index": 0, "verdict": "approved"}, {"index": 1, "verdict": "maybe"}]:
        with pytest.raises(ValueError):
            bench.decide(payload)
    assert bench.state["accepted"] == 0
    assert bench.state["iterations"][-1]["status"] == "pending"


def test_http_loop_and_write_boundary(tmp_path):
    server = make_server(Workbench(tmp_path), 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_port}") as client:
            assert client.get("/").status_code == 200
            assert client.get("/api/state").json()["accepted"] == 0
            response = client.post("/api/propose", json={"preset": "torpedoes"})
            assert response.status_code == 200
            assert response.json()["iterations"][-1]["status"] == "pending"
            response = client.post("/api/decide", json={"index": 1, "verdict": "approved"})
            assert response.json()["accepted"] == 1
            assert client.post("/api/propose", json={}, headers={"Origin": "https://example.org"}).status_code == 403
            assert client.post("/api/propose", content="{}").status_code == 415
            assert client.get("/workbench.json").status_code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_live_failure_does_not_create_revision(tmp_path, monkeypatch):
    def fail(*args):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr("rocinante.workbench.RefitAgent.propose", fail)
    bench = Workbench(tmp_path, live=True)
    with pytest.raises(RuntimeError):
        bench.propose({"ask": "more armor"})
    assert len(Workbench(tmp_path).state["iterations"]) == 1
