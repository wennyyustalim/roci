import pytest
from pydantic import ValidationError

from rocinante.samples import BASELINE
from rocinante.spec import FinSet, RocketSpec, json_schema


def test_baseline_is_valid():
    assert BASELINE.total_length_m == pytest.approx(0.55)
    assert BASELINE.caliber_m == pytest.approx(0.056)


def test_tip_chord_cannot_exceed_root():
    """model_copy skips validation, so validate the dump -- that is the path the
    agent's output takes."""
    bad = BASELINE.model_dump()
    bad["fins"]["root_chord_m"] = 0.03
    bad["fins"]["tip_chord_m"] = 0.05
    with pytest.raises(ValidationError):
        RocketSpec.model_validate(bad)


def test_fin_count_bounds():
    with pytest.raises(ValidationError):
        FinSet(count=2, root_chord_m=0.05, tip_chord_m=0.03, height_m=0.04)


def test_schema_is_serialisable():
    """The model is handed this. If it does not round-trip, the agent cannot answer."""
    import json

    assert json.loads(json.dumps(json_schema()))["title"] == "RocketSpec"


def test_spec_round_trips_through_json():
    assert RocketSpec.model_validate_json(BASELINE.model_dump_json()) == BASELINE
