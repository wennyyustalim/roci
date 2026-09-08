from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from openai import APIConnectionError

from rocinante.agent.refit import RefitAgent, RefitModelError, model_name
from rocinante.samples import ROCINANTE
from rocinante.ship import ShipSpec


class FakeResponses:
    def __init__(self, response):
        self.response = response
        self.request = None

    def parse(self, **kwargs):
        self.request = kwargs
        return self.response


class FakeClient:
    def __init__(self, response):
        self.responses = FakeResponses(response)


def changed_ship():
    after = ROCINANTE.model_copy(deep=True)
    after.weapons.magazine_m3 += after.weapons.torpedo_volume_m3
    after.rationale = "Add one magazine slot to carry one additional torpedo."
    return after


def test_propose_uses_responses_structured_output_contract():
    after = changed_ship()
    client = FakeClient(SimpleNamespace(output_parsed=after))

    proposed = RefitAgent(build_meshes=False, client=client).propose(
        ROCINANTE, "  carry another torpedo  "
    )

    assert proposed is after
    request = client.responses.request
    assert request["model"] == model_name()
    assert request["text_format"] is type(ROCINANTE)
    assert request["store"] is False
    assert request["input"][0]["role"] == "system"
    user_prompt = request["input"][1]["content"]
    assert "carry another torpedo" in user_prompt
    assert ROCINANTE.rationale not in user_prompt
    assert f"delta_v_km_s: {ROCINANTE.delta_v_km_s:,.2f}" in user_prompt


def test_propose_preserves_computed_physics_boundary():
    after = changed_ship()
    client = FakeClient(SimpleNamespace(output_parsed=after))
    proposed = RefitAgent(build_meshes=False, client=client).propose(ROCINANTE, "one more")

    assert proposed.weapons.torpedo_capacity == ROCINANTE.weapons.torpedo_capacity + 1
    assert proposed.delta_v_km_s < ROCINANTE.delta_v_km_s
    assert "delta_v_km_s" not in type(proposed).model_fields


@pytest.mark.parametrize("value", [None, "", "   "])
def test_blank_model_configuration_uses_default(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("ROCINANTE_MODEL", raising=False)
    else:
        monkeypatch.setenv("ROCINANTE_MODEL", value)
    assert model_name() == "gpt-6-astra"


def test_missing_api_key_fails_before_creating_client(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    create = Mock()
    monkeypatch.setattr("openai.OpenAI", create)

    with pytest.raises(RefitModelError, match="live refit needs OPENAI_API_KEY"):
        RefitAgent(build_meshes=False).propose(ROCINANTE, "change it")

    create.assert_not_called()


def test_refusal_has_a_clear_failure():
    refusal = SimpleNamespace(type="refusal", refusal="cannot comply")
    response = SimpleNamespace(
        output_parsed=None,
        output=[SimpleNamespace(content=[refusal])],
        incomplete_details=None,
        status="completed",
    )
    agent = RefitAgent(build_meshes=False, client=FakeClient(response))

    with pytest.raises(RefitModelError, match="refused the refit request"):
        agent.propose(ROCINANTE, "change it")


def test_incomplete_response_reports_reason():
    response = SimpleNamespace(
        output_parsed=None,
        output=[],
        incomplete_details=SimpleNamespace(reason="max_output_tokens"),
        status="incomplete",
    )
    agent = RefitAgent(build_meshes=False, client=FakeClient(response))

    with pytest.raises(RefitModelError, match="incomplete ShipSpec.*max_output_tokens"):
        agent.propose(ROCINANTE, "change it")


def test_api_connection_failure_is_actionable():
    class BrokenResponses:
        def parse(self, **kwargs):
            raise APIConnectionError(request=httpx.Request("POST", "https://api.openai.com"))

    client = SimpleNamespace(responses=BrokenResponses())
    agent = RefitAgent(build_meshes=False, client=client)

    with pytest.raises(RefitModelError, match="could not be reached before the timeout"):
        agent.propose(ROCINANTE, "change it")


def test_owned_sdk_client_is_closed(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    client = FakeClient(SimpleNamespace(output_parsed=changed_ship()))
    client.close = Mock()
    monkeypatch.setattr("openai.OpenAI", lambda **kwargs: client)

    RefitAgent(build_meshes=False).propose(ROCINANTE, "change it")

    client.close.assert_called_once_with()


def test_injected_sdk_client_remains_caller_owned():
    client = FakeClient(SimpleNamespace(output_parsed=changed_ship()))
    client.close = Mock()

    RefitAgent(build_meshes=False, client=client).propose(ROCINANTE, "change it")

    client.close.assert_not_called()


def test_domain_validation_failure_is_sanitized():
    class InvalidResponses:
        def parse(self, **kwargs):
            payload = ROCINANTE.model_dump()
            payload["hull"]["length_m"] = 1
            ShipSpec.model_validate(payload)

    agent = RefitAgent(
        build_meshes=False,
        client=SimpleNamespace(responses=InvalidResponses()),
    )

    with pytest.raises(RefitModelError, match="failed domain validation"):
        agent.propose(ROCINANTE, "change it")


@pytest.mark.parametrize("rationale", ["", "   "])
def test_blank_rationale_is_rejected(rationale):
    after = changed_ship().model_copy(update={"rationale": rationale})
    agent = RefitAgent(
        build_meshes=False,
        client=FakeClient(SimpleNamespace(output_parsed=after)),
    )
    with pytest.raises(RefitModelError, match="without a rationale"):
        agent.propose(ROCINANTE, "change it")


def test_no_op_proposal_is_rejected():
    after = ROCINANTE.model_copy(update={"rationale": "No engineering change was needed."})
    agent = RefitAgent(
        build_meshes=False,
        client=FakeClient(SimpleNamespace(output_parsed=after)),
    )
    with pytest.raises(RefitModelError, match="no-op ShipSpec"):
        agent.propose(ROCINANTE, "change it")
