from rocinante.diff import diff_specs
from rocinante.samples import BASELINE
from rocinante.spec import FinSet


def test_identical_specs_have_no_changes():
    assert diff_specs(BASELINE, BASELINE.model_copy(deep=True)).changes == []


def test_rationale_is_not_a_change():
    other = BASELINE.model_copy(deep=True, update={"rationale": "different words"})
    assert diff_specs(BASELINE, other).changes == []


def test_fin_change_names_the_fin_part():
    swept = BASELINE.model_copy(
        deep=True,
        update={"fins": FinSet(
            count=3, root_chord_m=0.06, tip_chord_m=0.03, height_m=0.045, sweep_m=0.042
        )},
    )
    d = diff_specs(BASELINE, swept)
    assert d.changed_parts == ["fin_*"]
    assert any("sweep_m" in c.path for c in d.changes)


def test_numeric_changes_report_a_delta():
    taller = BASELINE.model_copy(deep=True)
    taller.body[0].length_m = 0.24
    line = diff_specs(BASELINE, taller).changes[0].human()
    assert "+0.04" in line
