import json
import threading
from unittest.mock import Mock

import httpx
import pytest

from rocinante.agent.refit import RefitModelError
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


def test_http_loop_and_write_boundary(tmp_path, fake_blender):
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
            exported = client.post("/api/export", json={"index": 1})
            assert exported.json()["iterations"][1]["handoff"]["status"] == "exported"
            assert client.get("/exports/v0001/before.glb").content.startswith(b"glTF")
            assert client.get("/exports/v0001/comparison.json").json()["parent"] == 0
            assert client.get("/exports/v0001/workbench.json").status_code == 404
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


@pytest.fixture
def fake_blender(monkeypatch):
    def build(spec, path):
        path.write_bytes(b"glTF" + spec.model_dump_json().encode())
        return path

    monkeypatch.setattr("rocinante.handoff.build_ship_mesh", build)


def test_live_model_provenance_survives_config_change_reload_and_export(
    tmp_path, monkeypatch, fake_blender
):
    def propose(self, ship, ask):
        after = ship.model_copy(deep=True)
        after.hull.armor_cm += 1
        after.rationale = f"Live proposal for: {ask}"
        return after

    monkeypatch.setenv("ROCINANTE_MODEL", "gpt-6-astra-demo")
    monkeypatch.setattr("rocinante.workbench.RefitAgent.propose", propose)
    proposed = Workbench(tmp_path, live=True).propose({"ask": "add armor"})
    assert proposed["model"] == "gpt-6-astra-demo"
    assert proposed["iterations"][1]["model"] == "gpt-6-astra-demo"

    monkeypatch.setenv("ROCINANTE_MODEL", "gpt-6-astra-next")
    reloaded = Workbench(tmp_path, live=True)
    assert reloaded.snapshot()["model"] == "gpt-6-astra-next"
    assert reloaded.state["iterations"][1]["model"] == "gpt-6-astra-demo"

    exported = reloaded.export({"index": 1})
    assert exported["model"] == "gpt-6-astra-next"
    assert exported["iterations"][1]["model"] == "gpt-6-astra-demo"
    report = json.loads((tmp_path / "exports/v0001/comparison.json").read_text())
    assert report["model"] == "gpt-6-astra-demo"


def test_export_uses_parent_not_previous_rejected_revision(tmp_path, fake_blender):
    bench = Workbench(tmp_path)
    bench.propose({"preset": "armor"})
    bench.decide({"index": 1, "verdict": "rejected"})
    bench.propose({"preset": "drive"})
    state = bench.export({"index": 2})
    assert state["iterations"][2]["handoff"]["status"] == "exported"
    report = json.loads((tmp_path / "exports/v0002/comparison.json").read_text())
    assert report["parent"] == 0
    assert report["before"]["derived"] == ROCINANTE.derived()
    assert report["after"]["derived"] == ROCINANTE.derived()
    assert state["accepted"] == 0


def test_export_and_share_keep_the_accepted_parent_after_a_rejection(
    tmp_path, monkeypatch, fake_blender
):
    shared = {}
    client = Mock(base_url="https://work.withkord.com")

    def share_diff(before, after, title):
        shared.update(before=before.read_bytes(), after=after.read_bytes(), title=title)
        return {"url": "/d/accepted-parent"}

    client.share_diff.side_effect = share_diff
    monkeypatch.setattr("rocinante.workbench.KordClient", lambda: client)

    bench = Workbench(tmp_path)
    bench.propose({"preset": "torpedoes"})
    bench.decide({"index": 1, "verdict": "approved"})
    bench.propose({"preset": "armor"})
    bench.decide({"index": 2, "verdict": "rejected"})
    bench = Workbench(tmp_path)
    proposed = bench.propose({"preset": "drive"})["iterations"][3]

    assert proposed["parent"] == 1
    bench.export({"index": 3})
    state = bench.share({"index": 3})

    before = json.loads(shared["before"].removeprefix(b"glTF"))
    after = json.loads(shared["after"].removeprefix(b"glTF"))
    assert before == state["iterations"][1]["spec"]
    assert after == state["iterations"][3]["spec"]
    assert after["hull"]["armor_cm"] == before["hull"]["armor_cm"]
    assert shared["title"] == "Rocinante v1 → v3 (fixture)"
    assert state["accepted"] == 1
    assert state["iterations"][3]["status"] == "pending"

    report = json.loads((tmp_path / "exports/v0003/comparison.json").read_text())
    assert report["parent"] == 1
    assert report["artifacts"] == state["iterations"][3]["handoff"]["artifacts"]


def test_share_failure_retry_and_reload_do_not_lose_review(tmp_path, monkeypatch, fake_blender):
    client = Mock(base_url="https://work.withkord.com")
    client.share_diff.side_effect = [RuntimeError("network down"), {"url": "/d/example", "expiresAt": "later"}]
    monkeypatch.setattr("rocinante.workbench.KordClient", lambda: client)
    bench = Workbench(tmp_path)
    bench.propose({"preset": "drive"})
    bench.export({"index": 1})
    first = bench.share({"index": 1})
    assert first["iterations"][1]["handoff"]["status"] == "share_failed"
    assert first["iterations"][1]["status"] == "pending"
    bench = Workbench(tmp_path)
    second = bench.share({"index": 1})
    assert second["iterations"][1]["handoff"]["share_url"] == "https://work.withkord.com/d/example"
    Workbench(tmp_path).share({"index": 1})
    assert client.share_diff.call_count == 2
    assert client.close.call_count == 2
    assert second["accepted"] == 0


def test_modified_exports_cannot_be_shared(tmp_path, fake_blender):
    bench = Workbench(tmp_path)
    bench.propose({"preset": "drive"})
    bench.export({"index": 1})
    (tmp_path / "exports/v0001/after.glb").write_bytes(b"changed")
    with pytest.raises(ValueError, match="bytes changed"):
        bench.share({"index": 1})


def test_export_failure_preserves_proposal_and_can_retry(tmp_path, monkeypatch, fake_blender):
    bench = Workbench(tmp_path)
    bench.propose({"preset": "drive"})
    with monkeypatch.context() as patch:
        patch.setattr("rocinante.workbench.export_pair", Mock(side_effect=RuntimeError("Blender missing")))
        assert bench.export({"index": 1})["iterations"][1]["handoff"]["status"] == "export_failed"
    assert bench.export({"index": 1})["iterations"][1]["handoff"]["status"] == "exported"
    assert bench.state["iterations"][1]["status"] == "pending"


def test_interrupted_share_becomes_explicit_retry(tmp_path, fake_blender):
    bench = Workbench(tmp_path)
    bench.propose({"preset": "drive"})
    bench.export({"index": 1})
    bench.state["iterations"][1]["handoff"]["status"] = "sharing"
    bench.save()
    recovered = Workbench(tmp_path)
    assert recovered.state["iterations"][1]["handoff"]["status"] == "share_failed"


def test_interrupted_export_becomes_retryable_after_restart(tmp_path, fake_blender):
    bench = Workbench(tmp_path)
    bench.propose({"preset": "drive"})
    bench.state["iterations"][1]["handoff"] = {"status": "exporting"}
    bench.save()

    recovered = Workbench(tmp_path)
    handoff = recovered.state["iterations"][1]["handoff"]
    assert handoff["status"] == "export_failed"
    assert "interrupted" in handoff["error"].lower()
    assert recovered.state["iterations"][1]["status"] == "pending"
    assert recovered.export({"index": 1})["iterations"][1]["handoff"]["status"] == "exported"


def test_http_model_failure_returns_502_and_preserves_server_state(
    tmp_path, monkeypatch
):
    def fail(*args):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr("rocinante.workbench.RefitAgent.propose", fail)
    server = make_server(Workbench(tmp_path, live=True), 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_port}") as client:
            failed = client.post("/api/propose", json={"ask": "more armor"})
            assert failed.status_code == 502
            assert failed.json() == {
                "error": "Request failed. Check server logs; the accepted design is preserved."
            }
            state = client.get("/api/state")
            assert state.status_code == 200
            assert state.json()["accepted"] == 0
            assert len(state.json()["iterations"]) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join()

    assert len(Workbench(tmp_path).state["iterations"]) == 1


def test_http_refit_model_error_reaches_client_and_preserves_state(
    tmp_path, monkeypatch
):
    message = "gpt-6-astra authentication failed; set OPENAI_API_KEY"

    def fail(*args):
        raise RefitModelError(message)

    monkeypatch.setattr("rocinante.workbench.RefitAgent.propose", fail)
    server = make_server(Workbench(tmp_path, live=True), 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_port}") as client:
            failed = client.post("/api/propose", json={"ask": "more armor"})
            assert failed.status_code == 502
            assert failed.json() == {
                "error": f"{message}. The accepted design is preserved."
            }
            state = client.get("/api/state").json()
            assert state["accepted"] == 0
            assert len(state["iterations"]) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join()

    assert len(Workbench(tmp_path).state["iterations"]) == 1


def test_share_url_rejects_non_web_links():
    from rocinante.handoff import share_url

    for value in ("javascript:alert(1)", "", "file:///tmp/test"):
        with pytest.raises(ValueError):
            share_url("https://work.withkord.com", value)
