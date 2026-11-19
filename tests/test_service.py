"""Refresh scheduling, failure handling and snapshots in the telemetry service."""

import asyncio

from orbit_telemetry.config import Settings
from orbit_telemetry.metrics import Metrics
from orbit_telemetry.service import TelemetryService
from tests.conftest import ISS


def test_first_update_loads_every_satellite(loaded_service, settings):
    assert loaded_service.ready
    assert set(loaded_service.snapshots) == set(settings.norad_ids)


def test_elements_are_not_refetched_before_the_refresh_interval(loaded_service, source, clock):
    source.calls.clear()
    clock.advance(600)
    asyncio.run(loaded_service.update())
    assert source.calls == []  # respects CelesTrak fair use
    clock.advance(7200)
    asyncio.run(loaded_service.update())
    assert len(source.calls) == 5


def test_failed_fetch_keeps_previous_data_and_counts_the_failure(loaded_service, source, clock):
    source.failing.add(ISS)
    clock.advance(7200)
    asyncio.run(loaded_service.update())
    assert loaded_service.ready  # still serving the earlier elements
    failures = loaded_service.metrics.registry.get_sample_value(
        "celestrak_fetch_failures_total", {"norad_id": str(ISS)}
    )
    assert failures == 1


def test_data_becomes_stale_when_refreshes_keep_failing(loaded_service, source, clock):
    source.failing.update(source.records)
    clock.advance(6 * 3600 + 1)
    asyncio.run(loaded_service.update())
    assert loaded_service.snapshots[ISS].data_stale
    assert not loaded_service.orbital_data_ok(clock())


def test_not_ready_while_a_satellite_has_never_loaded(settings, source, clock):
    source.failing.add(ISS)
    service = TelemetryService(settings=settings, source=source, metrics=Metrics(), clock=clock)
    asyncio.run(service.update())
    assert not service.ready
    assert service.ready_count == 4


def test_snapshot_exports_domain_metrics(loaded_service):
    value = loaded_service.metrics.registry.get_sample_value(
        "satellite_battery_voltage_volts", {"norad_id": str(ISS), "name": "ISS (ZARYA)"}
    )
    assert value == loaded_service.snapshots[ISS].power.battery_voltage_v


def test_run_forever_survives_a_failing_update(source, clock, monkeypatch):
    settings = Settings(tick_seconds=0.01)
    service = TelemetryService(settings=settings, source=source, metrics=Metrics(), clock=clock)
    calls = {"n": 0}

    async def flaky_update():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")

    monkeypatch.setattr(service, "update", flaky_update)

    async def run_briefly():
        task = asyncio.create_task(service.run_forever())
        await asyncio.sleep(0.05)
        task.cancel()

    asyncio.run(run_briefly())
    assert calls["n"] >= 2  # kept looping after the first failure
