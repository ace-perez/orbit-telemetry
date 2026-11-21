"""Integration tests: the real container, over real HTTP, wired to its neighbours.

Run against the Compose stack (Phase 4) and against the Helm release in a kind cluster
(Phase 5, through `kubectl port-forward`, with INTEGRATION_EXPECTED_ENVIRONMENT=kind).

Unit tests (the rest of tests/) call the app in-process with fakes. These tests instead talk
to the running Compose stack, so they also prove what unit tests cannot: the image starts as
a non-root user, the app listens on the container network, CELESTRAK_BASE_URL reaches the
stub across that network, and Prometheus can scrape /metrics.

Skipped unless INTEGRATION_BASE_URL is set, so the normal test run stays offline:

    docker compose up --build --wait
    INTEGRATION_BASE_URL=http://localhost:8000 \\
    INTEGRATION_PROMETHEUS_URL=http://localhost:9090 \\
    uv run pytest tests/integration -v
"""

import os
import time
from collections.abc import Iterator

import httpx
import pytest

BASE_URL = os.environ.get("INTEGRATION_BASE_URL")
PROMETHEUS_URL = os.environ.get("INTEGRATION_PROMETHEUS_URL")
# The same tests run against Compose (Phase 4) and a kind cluster (Phase 5).
EXPECTED_ENVIRONMENT = os.environ.get("INTEGRATION_EXPECTED_ENVIRONMENT", "compose")
ISS = 25544

pytestmark = pytest.mark.skipif(not BASE_URL, reason="INTEGRATION_BASE_URL is not set")


def wait_for(check, timeout_s: float, what: str):
    """Poll `check` until it returns a truthy value or the timeout passes."""
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            result = check()
            if result:
                return result
        except httpx.HTTPError as error:  # not up yet
            last_error = error
        time.sleep(1)
    pytest.fail(f"{what} not reached within {timeout_s:.0f}s (last error: {last_error})")


@pytest.fixture(scope="module")
def client() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=BASE_URL, timeout=5) as http:
        # Ready means every satellite's orbital data was fetched from the stub.
        wait_for(lambda: http.get("/readyz").status_code == 200, 60, "/readyz 200")
        yield http


def test_liveness(client: httpx.Client) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_info_reflects_container_configuration(client: httpx.Client) -> None:
    info = client.get("/api/v1/info").json()
    # Set by compose.yaml or the Helm values, read from the environment by the app.
    assert info["environment"] == EXPECTED_ENVIRONMENT
    assert info["orbital_data_ok"] is True
    assert info["satellites_ready"] == info["satellites_tracked"] == 5


def test_all_satellites_loaded_through_the_stub(client: httpx.Client) -> None:
    satellites = client.get("/api/v1/satellites").json()
    assert {s["norad_id"] for s in satellites} == {25544, 20580, 40697, 33591, 49260}


def test_telemetry_is_physically_plausible(client: httpx.Client) -> None:
    telemetry = client.get(f"/api/v1/satellites/{ISS}/telemetry").json()
    position = telemetry["position"]
    assert -90 <= position["latitude_deg"] <= 90
    assert -180 <= position["longitude_deg"] <= 180
    assert 300 < position["altitude_km"] < 500  # the ISS flies at roughly 400 km
    assert 7.0 < position["speed_km_s"] < 8.0
    assert telemetry["data_stale"] is False


def test_positions_move_between_ticks(client: httpx.Client) -> None:
    # TICK_SECONDS=1 in compose.yaml: proves the background loop runs inside the container.
    def longitude() -> float:
        return client.get(f"/api/v1/satellites/{ISS}/telemetry").json()["position"]["longitude_deg"]

    first = longitude()
    assert wait_for(lambda: longitude() != first, 10, "a new ISS position")


def test_unknown_satellite_is_404(client: httpx.Client) -> None:
    assert client.get("/api/v1/satellites/1/telemetry").status_code == 404


def test_console_page_and_its_files_are_served(client: httpx.Client) -> None:
    """The image carries the page and the vendored files (package data in the wheel)."""
    page = client.get("/")
    assert page.status_code == 200
    assert "default-src 'self'" in page.headers["content-security-policy"]
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/vendor/d3.min.js").status_code == 200


def test_metrics_exposed(client: httpx.Client) -> None:
    body = client.get("/metrics").text
    assert "orbit_telemetry_build_info" in body
    assert "http_requests_total" in body
    assert "satellite_altitude_km" in body


@pytest.mark.skipif(not PROMETHEUS_URL, reason="INTEGRATION_PROMETHEUS_URL is not set")
def test_prometheus_scrapes_the_app() -> None:
    def target_up() -> bool:
        response = httpx.get(
            f"{PROMETHEUS_URL}/api/v1/query", params={"query": 'up{job="orbit-telemetry"}'}
        )
        results = response.json()["data"]["result"]
        return bool(results) and results[0]["value"][1] == "1"

    assert wait_for(target_up, 30, 'up{job="orbit-telemetry"} == 1')
