"""Shared test fixtures: a fixed clock, a fake CelesTrak, and a ready-made app.

Nothing here touches the network or the real clock, so every run gives the same result.
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from orbit_telemetry.celestrak import CelesTrakError
from orbit_telemetry.config import Settings
from orbit_telemetry.main import create_app
from orbit_telemetry.metrics import Metrics
from orbit_telemetry.service import TelemetryService

FIXTURES = Path(__file__).parent / "fixtures"
EPOCH = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)  # epoch of every fixture element set
ISS = 25544


@pytest.fixture
def omm_records() -> dict[int, dict]:
    raw = json.loads((FIXTURES / "omm.json").read_text())
    return {int(k): v for k, v in raw.items()}


class FakeSource:
    """Stands in for CelesTrakClient. Can be told to fail for chosen satellites."""

    def __init__(self, records: dict[int, dict]) -> None:
        self.records = records
        self.failing: set[int] = set()
        self.calls: list[int] = []

    async def fetch(self, norad_id: int) -> dict:
        self.calls.append(norad_id)
        if norad_id in self.failing:
            raise CelesTrakError("simulated outage")
        return self.records[norad_id]


class FakeClock:
    """A clock tests can move forward explicitly."""

    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(EPOCH + timedelta(minutes=30))


@pytest.fixture
def source(omm_records: dict[int, dict]) -> FakeSource:
    return FakeSource(omm_records)


@pytest.fixture
def settings() -> Settings:
    return Settings(environment="test")


@pytest.fixture
def service(settings: Settings, source: FakeSource, clock: FakeClock) -> TelemetryService:
    return TelemetryService(settings=settings, source=source, metrics=Metrics(), clock=clock)


@pytest.fixture
def loaded_service(service: TelemetryService) -> TelemetryService:
    asyncio.run(service.update())
    return service


@pytest.fixture
def client(settings: Settings, loaded_service: TelemetryService):
    app = create_app(settings=settings, service=loaded_service, start_background=False)
    with TestClient(app) as test_client:
        yield test_client
