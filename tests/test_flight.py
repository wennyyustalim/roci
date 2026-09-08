"""The flight model. Cheap tests, and they catch the sign errors that would
otherwise show up on stage."""

import math

import pytest

from rocinante.flight import distance_between, plan, solve
from rocinante.samples import ROCINANTE
from rocinante.ship import G0


def test_flip_is_half_the_trip():
    burn = solve("Tycho", "Ceres", accel_g=1 / 3)
    assert burn.flip_time_s == pytest.approx(burn.total_time_s / 2)


def test_distance_is_recovered_from_the_solution():
    """The whole point of a closed form: integrate it back and land on d."""
    burn = solve("Tycho", "Ceres", accel_g=1 / 3)
    assert burn.position_at(burn.total_time_s) == pytest.approx(burn.distance_m, rel=1e-9)
    assert burn.position_at(burn.flip_time_s) == pytest.approx(burn.distance_m / 2, rel=1e-9)


def test_velocity_peaks_at_the_flip_and_returns_to_zero():
    burn = solve("Tycho", "Ceres", accel_g=1 / 3)
    assert burn.velocity_at(burn.flip_time_s) == pytest.approx(burn.peak_velocity_ms)
    assert burn.velocity_at(burn.total_time_s) == pytest.approx(0.0, abs=1e-6)
    assert burn.delta_v_km_s == pytest.approx(2 * burn.peak_velocity_ms / 1000)


def test_harder_burn_is_faster_and_costs_more_delta_v():
    slow = solve("Tycho", "Ceres", accel_g=1 / 3)
    fast = solve("Tycho", "Ceres", accel_g=5.0)
    assert fast.total_time_s < slow.total_time_s
    assert fast.delta_v_km_s > slow.delta_v_km_s
    # Both scale as sqrt(a): quadrupling the g halves the time.
    assert slow.total_time_s / fast.total_time_s == pytest.approx(math.sqrt(15.0), rel=1e-9)


def test_legs_are_symmetric():
    assert distance_between("Tycho", "Ceres") == distance_between("Ceres", "Tycho")


def test_unknown_leg_is_an_error_not_a_guess():
    with pytest.raises(KeyError):
        distance_between("Tycho", "Luna")


def test_zero_acceleration_is_rejected():
    with pytest.raises(ValueError):
        solve("Tycho", "Ceres", accel_g=0)


def test_plan_warns_when_the_crew_cannot_take_it():
    burn = plan(ROCINANTE, "Tycho", "Ceres", accel_g=10.0)
    assert any("crew limit" in w for w in burn.warnings)


def test_plan_warns_when_the_ship_lacks_delta_v():
    burn = plan(ROCINANTE, "Ceres", "Ring", accel_g=1 / 3)
    assert any("short" in w for w in burn.warnings)


def test_accel_g_converts_to_ms2():
    assert solve("Tycho", "Ceres", accel_g=1.0).accel_ms2 == pytest.approx(G0)
