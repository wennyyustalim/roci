"""The contract that has to hold before anything else matters.

`test_writer_output_opens_in_openrocket` is the real gate and it is skipped
until you drop a reference file in tests/fixtures/. Do that first on the day.
"""

import zipfile
from pathlib import Path

import pytest

from rocinante.ork import read_ork, write_ork
from rocinante.samples import BASELINE

FIXTURES = Path(__file__).parent / "fixtures"


def test_ork_is_a_zip_holding_rocket_ork(tmp_path):
    path = write_ork(BASELINE, tmp_path / "r.ork")
    with zipfile.ZipFile(path) as zf:
        assert "rocket.ork" in zf.namelist()
        assert b"<openrocket" in zf.read("rocket.ork")


def test_geometry_survives_the_round_trip(tmp_path):
    back = read_ork(write_ork(BASELINE, tmp_path / "r.ork"))

    assert back.nose.length_m == pytest.approx(BASELINE.nose.length_m)
    assert back.nose.base_radius_m == pytest.approx(BASELINE.nose.base_radius_m)
    assert back.nose.shape == BASELINE.nose.shape
    assert len(back.body) == len(BASELINE.body)
    assert back.body[0].length_m == pytest.approx(BASELINE.body[0].length_m)
    assert back.fins.count == BASELINE.fins.count
    assert back.fins.root_chord_m == pytest.approx(BASELINE.fins.root_chord_m)
    assert back.fins.sweep_m == pytest.approx(BASELINE.fins.sweep_m)


def test_ballast_survives_the_round_trip(tmp_path):
    spec = BASELINE.model_copy(deep=True, update={"nose_ballast_kg": 0.012})
    assert read_ork(write_ork(spec, tmp_path / "r.ork")).nose_ballast_kg == pytest.approx(0.012)


@pytest.mark.skipif(
    not (FIXTURES / "reference.ork").exists(),
    reason="drop a real OpenRocket export in tests/fixtures/reference.ork",
)
def test_reference_file_parses():
    spec = read_ork(FIXTURES / "reference.ork")
    assert spec.total_length_m > 0
    assert spec.fins.count >= 3
