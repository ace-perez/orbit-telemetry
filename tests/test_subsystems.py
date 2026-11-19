"""The simulated power and thermal model behaves like a real spacecraft would."""

import pytest

from orbit_telemetry.subsystems import SubsystemConfig, SubsystemSimulator


def test_battery_charges_in_sunlight():
    sim = SubsystemSimulator(state_of_charge_pct=50)
    # Readings are reported to 1 decimal place, hence the tolerance.
    assert sim.step(100, sunlit=True).state_of_charge_pct == pytest.approx(50.75, abs=0.05)


def test_battery_drains_in_eclipse_and_array_output_drops_to_zero():
    reading = SubsystemSimulator(state_of_charge_pct=50).step(100, sunlit=False)
    assert reading.state_of_charge_pct == pytest.approx(48.8)
    assert reading.solar_array_current_a == 0.0


def test_state_of_charge_is_clamped():
    cfg = SubsystemConfig()
    full = SubsystemSimulator(state_of_charge_pct=99.9)
    for _ in range(10):
        full.step(300, sunlit=True)
    assert full.reading().state_of_charge_pct == cfg.soc_max_pct

    empty = SubsystemSimulator(state_of_charge_pct=21)
    for _ in range(10):
        empty.step(300, sunlit=False)
    assert empty.reading().state_of_charge_pct == cfg.soc_min_pct


def test_bus_voltage_tracks_state_of_charge():
    assert SubsystemSimulator(state_of_charge_pct=75).reading().battery_voltage_v == 27.95


def test_long_pauses_are_capped():
    sim = SubsystemSimulator(state_of_charge_pct=50)
    sim.step(10_000, sunlit=True)  # treated as max_step_s (300 s)
    assert sim.reading().state_of_charge_pct == pytest.approx(52.25, abs=0.05)


def test_temperature_moves_towards_equilibrium_without_overshooting():
    sim = SubsystemSimulator(temperature_c=18)
    warmer = sim.step(300, sunlit=True).core_temperature_c
    assert 18 < warmer < 22
    for _ in range(50):
        sim.step(300, sunlit=False)
    assert sim.reading().core_temperature_c == pytest.approx(8, abs=0.1)
