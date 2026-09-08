import pytest

from rocinante.diff import diff_ships, diff_specs, ship_geometry_parts
from rocinante.samples import BASELINE, ROCINANTE
from rocinante.ship import DeckKind
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


def test_torpedo_tubes_change_geometry_but_propellant_does_not():
    tubes = ROCINANTE.model_copy(deep=True)
    tubes.weapons.torpedo_tubes += 2
    assert ship_geometry_parts(ROCINANTE, tubes) == ["tube_*"]

    fueled = ROCINANTE.model_copy(deep=True)
    fueled.drive.propellant_t *= 1.1
    fueled.drive.max_thrust_kn *= 1.1
    assert ship_geometry_parts(ROCINANTE, fueled) == []


def test_armor_affects_the_hull_assembly_but_not_generated_geometry():
    armored = ROCINANTE.model_copy(deep=True)
    armored.hull.armor_cm += 2.0
    armored.hull.skin_kg_m2 *= 1.1

    assert diff_ships(ROCINANTE, armored).changed_parts == ["hull_body"]
    assert ship_geometry_parts(ROCINANTE, armored) == []


@pytest.mark.parametrize("field", ["cone_length_m", "cone_radius_m"])
def test_drive_cone_dimensions_change_drive_geometry(field):
    after = ROCINANTE.model_copy(deep=True)
    setattr(after.drive, field, getattr(after.drive, field) + 1.0)
    assert ship_geometry_parts(ROCINANTE, after) == ["drive_*"]


def test_pdc_mount_count_names_the_pdc_assembly_and_geometry():
    after = ROCINANTE.model_copy(deep=True)
    after.weapons.pdc_mounts += 2

    assert diff_ships(ROCINANTE, after).changed_parts == ["pdc_*"]
    assert ship_geometry_parts(ROCINANTE, after) == ["pdc_*"]


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("length_m", ["deck_*", "hull_body", "pdc_*", "tube_*"]),
        ("beam_m", ["deck_*", "drive_*", "hull_body", "pdc_*", "tube_*"]),
        ("taper", ["deck_*", "hull_body", "pdc_*", "tube_*"]),
    ],
)
def test_hull_dimensions_change_dependent_geometry(field, expected):
    after = ROCINANTE.model_copy(deep=True)
    setattr(after.hull, field, getattr(after.hull, field) * 1.01)
    assert ship_geometry_parts(ROCINANTE, after) == expected


@pytest.mark.parametrize("change", ["count", "height", "kind"])
def test_deck_count_height_and_kind_change_deck_geometry(change):
    after = ROCINANTE.model_copy(deep=True)
    if change == "count":
        after.decks.append(after.decks[-1].model_copy())
    elif change == "height":
        after.decks[0].height_m += 0.25
    else:
        after.decks[0].kind = DeckKind.CARGO

    assert ship_geometry_parts(ROCINANTE, after) == ["deck_*"]


def test_deck_metadata_does_not_change_geometry():
    after = ROCINANTE.model_copy(deep=True)
    after.decks[0].name = "Renamed deck"
    after.decks[0].detailed = not after.decks[0].detailed
    assert ship_geometry_parts(ROCINANTE, after) == []
