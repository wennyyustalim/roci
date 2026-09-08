"""ShipSpec's derived properties. Every one of these is a number that moves on
screen during the refit beat, so a wrong sign here is a wrong demo."""

import math

import pytest

from rocinante.diff import diff_ships
from rocinante.samples import ROCINANTE
from rocinante.ship import CrewMember, ShipSpec


def test_delta_v_is_the_rocket_equation():
    s = ROCINANTE
    expected = s.drive.exhaust_velocity_km_s * math.log(s.wet_mass_t / s.dry_mass_t)
    assert s.delta_v_km_s == pytest.approx(expected)


def test_wet_mass_is_dry_plus_propellant():
    assert ROCINANTE.wet_mass_t == pytest.approx(
        ROCINANTE.dry_mass_t + ROCINANTE.drive.propellant_t
    )


def test_armor_costs_delta_v():
    """Dead mass raises the dry mass only, so the mass ratio falls."""
    heavier = ROCINANTE.model_copy(deep=True)
    heavier.hull.armor_cm = ROCINANTE.hull.armor_cm * 2
    assert heavier.dry_mass_t > ROCINANTE.dry_mass_t
    assert heavier.delta_v_km_s < ROCINANTE.delta_v_km_s
    assert heavier.max_accel_g < ROCINANTE.max_accel_g


def test_propellant_buys_delta_v_and_costs_acceleration():
    fuller = ROCINANTE.model_copy(deep=True)
    fuller.drive.propellant_t = ROCINANTE.drive.propellant_t * 1.5
    assert fuller.delta_v_km_s > ROCINANTE.delta_v_km_s
    assert fuller.max_accel_g < ROCINANTE.max_accel_g


def test_torpedo_capacity_is_magazine_plus_tubes():
    w = ROCINANTE.weapons
    assert w.torpedo_capacity == int(w.magazine_m3 // w.torpedo_volume_m3) + w.torpedo_tubes


def test_decimal_magazine_does_not_lose_a_slot():
    from rocinante.ship import Weapons

    assert Weapons(magazine_m3=105.6, torpedo_tubes=6).torpedo_capacity == 28
    assert Weapons(magazine_m3=105.5, torpedo_tubes=6).torpedo_capacity == 27


def test_the_weakest_crew_member_sets_the_limit():
    assert ROCINANTE.crew_g_limit == min(c.juiced_g_tolerance for c in ROCINANTE.crew)
    assert ROCINANTE.crew_limited


def test_a_ship_with_no_crew_is_drive_limited():
    empty = ROCINANTE.model_copy(deep=True, update={"crew": []})
    assert empty.crew_g_limit == pytest.approx(empty.max_accel_g)
    assert not empty.crew_limited


def test_decks_must_fit_the_hull():
    with pytest.raises(ValueError):
        ShipSpec(
            hull=ROCINANTE.hull.model_copy(update={"length_m": 6.0}),
            decks=ROCINANTE.decks,
        )


def test_diff_names_the_parts_the_viewer_lights():
    after = ROCINANTE.model_copy(deep=True)
    after.drive.cone_length_m += 4.0
    d = diff_ships(ROCINANTE, after)
    assert d.changed_parts == ["drive_*"]
    assert any("cone_length_m" in c.path for c in d.changes)


def test_rationale_is_not_a_design_change():
    """Two ships differing only in prose must diff to nothing."""
    after = ROCINANTE.model_copy(deep=True, update={"rationale": "different words"})
    assert diff_ships(ROCINANTE, after).changes == []


def test_crew_mass_reaches_the_dry_mass():
    heavy = ROCINANTE.model_copy(deep=True)
    heavy.crew = [*ROCINANTE.crew, CrewMember(name="Extra", role="passenger")]
    assert heavy.dry_mass_t > ROCINANTE.dry_mass_t
