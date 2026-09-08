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
    assert first["geometry_changed_parts"] == ["tube_*"]
    assert bench.state["accepted"] == 0
    with pytest.raises(ValueError, match="pending"):
        bench.propose({"preset": "armor"})
    bench.decide({"index": 1, "verdict": "approved"})
    bench = Workbench(tmp_path)
    second = bench.propose({"preset": "armor"})["iterations"][-1]
    assert second["parent"] == 1
    assert second["derived"]["delta_v_km_s"] < first["derived"]["delta_v_km_s"]
    assert second["mission"]["total_time_s"] == first["mission"]["total_time_s"]
    assert second["geometry_changed_parts"] == []
    bench.decide({"index": 2, "verdict": "rejected"})
    third = bench.propose({"preset": "drive"})["iterations"][-1]
    assert third["parent"] == 1
    assert third["spec"]["hull"]["armor_cm"] == ROCINANTE.hull.armor_cm
    assert third["derived"] == first["derived"]
    assert third["changed_parts"] == ["drive_*"]
    assert third["geometry_changed_parts"] == ["drive_*"]


def test_older_revision_geometry_metadata_is_recovered_from_its_parent(tmp_path):
    bench = Workbench(tmp_path)
    bench.propose({"preset": "armor"})
    bench.decide({"index": 1, "verdict": "rejected"})
    bench.propose({"preset": "drive"})
    for entry in bench.state["iterations"]:
        entry.pop("geometry_changed_parts")
    bench.save()
    recovered = Workbench(tmp_path).snapshot()
    assert recovered["iterations"][1]["geometry_changed_parts"] == []
    assert recovered["iterations"][2]["geometry_changed_parts"] == ["drive_*"]
    assert recovered["iterations"][2]["parent"] == 0


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


def test_blender_scene_spec_tracks_pending_and_restores_accepted_ship(tmp_path):
    bench = Workbench(tmp_path)
    baseline = json.loads((tmp_path / "blender-current.json").read_text())
    assert baseline == ROCINANTE.model_dump(mode="json")

    pending = bench.propose({"preset": "drive"})["iterations"][-1]
    assert json.loads((tmp_path / "blender-current.json").read_text()) == pending["spec"]

    bench.decide({"index": 1, "verdict": "rejected"})
    assert json.loads((tmp_path / "blender-current.json").read_text()) == baseline


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
    assert shared["title"] == "Rocinante ship v1 → v3 (fixture)"
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


def test_torpedo_rides_with_the_ship_and_reaches_openrocket(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr("rocinante.openrocket_live.show_in_openrocket",
                        lambda path, selection, bounds=None: opened.append((path, json.loads(selection.read_text())["name"])) or {"status": "synced"})
    bench = Workbench(tmp_path, show_openrocket=True)
    assert opened == [(tmp_path / "torpedo" / "v0000.ork", "Rocinante general torpedo v0")]
    assert bench.state["iterations"][0]["torpedo"]["fins"] == ROCINANTE.torpedo.fins.count

    armor = bench.propose({"preset": "armor"})["iterations"][-1]
    assert armor["torpedo"]["changed"] is False
    assert len(opened) == 2  # Updates use the bridge; no window is opened or closed.
    bench.decide({"index": 1, "verdict": "rejected"})

    fins = bench.propose({"preset": "fins"})["iterations"][-1]
    assert fins["torpedo"]["changed"] is True
    assert fins["changed_parts"] == ["torpedo"]
    assert fins["geometry_changed_parts"] == []
    assert fins["derived"] == bench.state["iterations"][0]["derived"]
    assert opened[-1] == (tmp_path / "torpedo" / "v0002.ork", "Rocinante general torpedo v2")
    from rocinante.ork import read_ork
    assert read_ork(opened[-1][0]).fins.sweep_m == pytest.approx(ROCINANTE.torpedo.fins.sweep_m + 0.01)

    bench.decide({"index": 2, "verdict": "rejected"})
    assert opened[-1][1] == "Rocinante general torpedo v0"  # back to the accepted torpedo


def test_auto_export_gives_the_viewer_real_geometry_for_every_revision(tmp_path, fake_blender):
    bench = Workbench(tmp_path, auto_export=True)
    baseline = bench.state["iterations"][0]["handoff"]
    assert baseline["status"] == "baseline" and set(baseline["artifacts"]) == {"after"}
    assert (tmp_path / "exports" / "v0000" / "after.glb").read_bytes().startswith(b"glTF")

    proposal = bench.propose({"preset": "drive"})["iterations"][-1]
    assert proposal["handoff"]["status"] == "exported"
    assert (tmp_path / "exports" / "v0001" / "before.glb").exists()
    # A reload neither re-exports the baseline nor loses the pair.
    reloaded = Workbench(tmp_path, auto_export=True).state["iterations"]
    assert reloaded[0]["handoff"]["artifacts"] == baseline["artifacts"]
    assert reloaded[1]["handoff"]["status"] == "exported"


def test_demo_mode_accepts_every_ask_and_shares_the_right_pair(tmp_path, monkeypatch, fake_blender):
    shared, shown = [], []
    client = Mock(base_url="https://work.withkord.com")
    client.share_diff.side_effect = lambda before, after, title: (
        shared.append((before.name, after.name, title)) or {"url": f"/d/{len(shared)}"}
    )
    monkeypatch.setattr("rocinante.workbench.KordClient", lambda: client)
    monkeypatch.setattr("rocinante.workbench.threading.Thread",
                        lambda target, args, name, daemon: Mock(start=lambda: target(*args)))
    bench = Workbench(tmp_path, auto_export=True, auto_accept=True, auto_share=True,
                      on_share_url=lambda url, index: shown.append((url, index)))
    fins = bench.propose({"preset": "fins"})["iterations"][-1]
    assert fins["status"] == "approved" and bench.state["accepted"] == 1
    assert shared[-1] == ("v0000.ork", "v0001.ork", "Rocinante torpedo v0 → v1 (fixture)")
    assert fins["handoff"]["compared"] == "torpedo"
    tubes = bench.propose({"preset": "torpedoes"})["iterations"][-1]
    assert tubes["parent"] == 1 and bench.state["accepted"] == 2
    assert shared[-1] == ("before.glb", "after.glb", "Rocinante ship v1 → v2 (fixture)")
    # Each link carries its revision, so a late one can be told from a newer one.
    assert shown == [("https://work.withkord.com/d/1", 1), ("https://work.withkord.com/d/2", 2)]
    bow = bench.propose({"preset": "bow"})["iterations"][-1]
    assert bow["geometry_changed_parts"] == ["tube_*"]
    assert bow["spec"]["weapons"]["tube_station"] == 0.88


def test_demo_torpedo_refit_keeps_ship_and_crew_static(tmp_path):
    bench = Workbench(tmp_path, torpedo_only=True, auto_accept=True)
    baseline = bench.snapshot()["iterations"][0]
    for preset in ("fins", "nose", "four_fins"):
        result = bench.propose({"preset": preset})["iterations"][-1]
        for field in ("name", "hull", "drive", "weapons", "decks", "crew"):
            assert result["spec"][field] == baseline["spec"][field]
        assert result["geometry_changed_parts"] == []
        assert result["torpedo"]["changed"]
    assert "armor" not in bench.snapshot()["presets"]
    with pytest.raises(ValueError, match="supported"):
        bench.propose({"preset": "armor"})


@pytest.mark.parametrize("field", ["hull", "drive", "weapons", "decks", "crew"])
def test_demo_rejects_model_ship_edits_before_writing(tmp_path, monkeypatch, field):
    bench = Workbench(tmp_path, live=True, torpedo_only=True, auto_accept=True)
    original_state = bench.path.read_bytes()
    original_blender = bench.blender_spec_path.read_bytes()

    def proposal(self, ship, ask):
        assert self.torpedo_only
        after = ship.model_copy(deep=True)
        after.torpedo.nose.length_m += .05
        if field == "hull":
            after.hull.length_m += 1
        elif field == "drive":
            after.drive.propellant_t += 1
        elif field == "weapons":
            after.weapons.torpedo_tubes += 1
        elif field == "decks":
            after.decks[0].name = "Changed"
        else:
            after.crew[0].name = "Changed"
        return after

    monkeypatch.setattr("rocinante.workbench.RefitAgent.propose", proposal)
    with pytest.raises(ValueError, match="Roci is static"):
        bench.propose({"ask": "Change my torpedo"})
    assert bench.path.read_bytes() == original_state
    assert bench.blender_spec_path.read_bytes() == original_blender
    assert len(bench.state["iterations"]) == 1


def test_selected_round_refit_is_isolated_and_survives_reload(tmp_path):
    bench = Workbench(tmp_path, auto_accept=True)
    first = bench.select({"torpedo_id": "torpedo_01"})
    assert first["selected_torpedo"] == "torpedo_01"
    assert set(first["presets"]) == {"fins", "nose", "four_fins"}
    changed = bench.propose({"preset": "nose", "torpedo_id": "torpedo_01"})["iterations"][-1]
    assert changed["target_torpedo"] == "torpedo_01"
    assert changed["spec"]["torpedo"] == ROCINANTE.torpedo.model_dump(mode="json")
    assert changed["torpedoes"]["torpedo_01"]["nose"]["length_m"] == pytest.approx(.15)
    assert bench.select({"torpedo_id": "torpedo_02"})["workshop_torpedo"]["length_m"] == pytest.approx(ROCINANTE.torpedo.total_length_m)
    second = bench.propose({"preset": "four_fins"})["iterations"][-1]
    assert second["torpedoes"]["torpedo_01"] == changed["torpedoes"]["torpedo_01"]
    assert second["torpedoes"]["torpedo_02"]["fins"]["count"] == 4
    reloaded = Workbench(tmp_path, auto_accept=True)
    assert reloaded.snapshot()["selected_torpedo"] == "torpedo_02"
    assert reloaded.snapshot()["workshop_torpedo"]["fins"] == 4
    reloaded.select({"torpedo_id": None})
    general = reloaded.propose({"preset": "armor", "torpedo_id": None})["iterations"][-1]
    assert general["spec"]["hull"]["armor_cm"] == ROCINANTE.hull.armor_cm + 2
    assert general["torpedoes"] == second["torpedoes"]


def test_selection_validates_identity_without_creating_revisions(tmp_path):
    bench = Workbench(tmp_path, auto_accept=True)
    before = bench.path.read_bytes()
    for target in ("torpedo_99", "../torpedo_01", 1, [], {}):
        with pytest.raises(ValueError):
            bench.select({"torpedo_id": target})
        assert bench.path.read_bytes() == before
    bench.select({"torpedo_id": "torpedo_01"})
    assert len(bench.state["iterations"]) == 1
    assert json.loads(bench.selection_path.read_text())["torpedo_id"] == "torpedo_01"
    with pytest.raises(ValueError):
        bench.propose({"preset": "armor"})
    assert len(bench.state["iterations"]) == 1


def test_selected_round_cannot_modify_ship_and_rejection_restores_round(tmp_path, monkeypatch):
    bench = Workbench(tmp_path, live=True)
    bench.select({"torpedo_id": "torpedo_01"})
    def malicious(self, ship, ask):
        result = ship.model_copy(deep=True)
        result.hull.armor_cm += 2
        result.torpedo.nose.length_m += .05
        return result
    monkeypatch.setattr("rocinante.workbench.RefitAgent.propose", malicious)
    with pytest.raises(ValueError, match="static"):
        bench.propose({"ask": "Refit this round"})
    assert len(bench.state["iterations"]) == 1
    bench.live = False
    bench.propose({"preset": "nose"})
    assert bench.snapshot()["workshop_torpedo"]["length_m"] == pytest.approx(.60)
    bench.decide({"index": 1, "verdict": "rejected"})
    assert bench.snapshot()["workshop_torpedo"]["length_m"] == pytest.approx(.55)


def test_http_selection_and_general_scope(tmp_path):
    server = make_server(Workbench(tmp_path, auto_accept=True), 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_port}") as client:
            assert client.post("/api/select", json={"torpedo_id":"torpedo_02"}).json()["selected_torpedo"] == "torpedo_02"
            refit = client.post("/api/propose", json={"preset":"nose", "torpedo_id":"torpedo_02"}).json()
            assert refit["iterations"][-1]["target_torpedo"] == "torpedo_02"
            assert client.post("/api/select", json={"torpedo_id":None}).json()["selected_torpedo"] is None
            assert client.post("/api/select", json={"torpedo_id":"bogus"}).status_code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
