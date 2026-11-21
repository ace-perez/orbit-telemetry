"""HTTP API behaviour through FastAPI's test client."""

from fastapi.testclient import TestClient

from orbit_telemetry.config import Settings
from orbit_telemetry.main import create_app
from orbit_telemetry.metrics import Metrics
from orbit_telemetry.service import TelemetryService
from tests.conftest import ISS


def test_liveness(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_ready_when_all_satellites_loaded(client):
    assert client.get("/readyz").status_code == 200


def test_not_ready_before_data_loads(settings, source, clock):
    service = TelemetryService(settings=settings, source=source, metrics=Metrics(), clock=clock)
    app = create_app(settings=settings, service=service, start_background=False)
    with TestClient(app) as c:
        response = c.get("/readyz")
        assert response.status_code == 503
        assert response.json()["expected"] == 5
        assert c.get(f"/api/v1/satellites/{ISS}/telemetry").status_code == 503


def test_info(client):
    body = client.get("/api/v1/info").json()
    assert body["propagator"] == "SGP4"
    assert body["satellites_tracked"] == body["satellites_ready"] == 5
    assert body["orbital_data_ok"] is True


def test_satellite_list(client):
    body = client.get("/api/v1/satellites").json()
    assert [s["norad_id"] for s in body] == [25544, 20580, 40697, 33591, 49260]
    assert {s["orbit_class"] for s in body} >= {"LEO", "SSO"}


def test_telemetry_has_every_field_the_page_binds(client):
    body = client.get(f"/api/v1/satellites/{ISS}/telemetry").json()
    assert body["intl_designator"] == "1998-067A"
    assert body["position"]["frame"] == "WGS-84 geodetic"
    assert set(body["position"]) >= {"latitude_deg", "longitude_deg", "altitude_km", "speed_km_s"}
    assert set(body["power"]) >= {
        "sunlit",
        "battery_voltage_v",
        "state_of_charge_pct",
        "solar_array_current_a",
        "bands",
    }
    assert body["thermal"]["target_temperature_c"] == 18.0
    assert body["simulated_fields"] == ["power", "thermal"]
    assert 0 < body["coverage_half_angle_deg"] < 30


def test_unknown_satellite_is_404(client):
    assert client.get("/api/v1/satellites/99999/telemetry").status_code == 404


def test_track_defaults_to_three_orbits(client):
    body = client.get(f"/api/v1/satellites/{ISS}/track").json()
    assert body["orbits"] == 3
    assert len(body["points"]) > 270  # about 93 points per orbit at 60 s steps


def test_track_rejects_out_of_range_parameters(client):
    assert client.get(f"/api/v1/satellites/{ISS}/track?orbits=4").status_code == 422
    assert client.get(f"/api/v1/satellites/{ISS}/track?step_seconds=1").status_code == 422


def test_sun_endpoint(client):
    body = client.get("/api/v1/sun").json()
    assert -23.5 <= body["subsolar_latitude_deg"] <= 23.5


def test_metrics_expose_red_and_domain_series(client):
    client.get("/api/v1/satellites")
    text = client.get("/metrics").text
    assert 'http_requests_total{method="GET",route="/api/v1/satellites",status="200"}' in text
    assert "satellite_battery_soc_percent" in text
    assert 'orbit_telemetry_build_info{version="0.1.0"} 1.0' in text


def test_request_id_is_echoed_or_generated(client):
    assert client.get("/healthz", headers={"x-request-id": "abc"}).headers["x-request-id"] == "abc"
    assert len(client.get("/healthz").headers["x-request-id"]) == 32


def test_failure_injection_hits_api_but_not_probes(loaded_service):
    settings = Settings(failure_rate=1.0)
    app = create_app(settings=settings, service=loaded_service, start_background=False)
    with TestClient(app) as c:
        assert c.get("/api/v1/satellites").status_code == 500
        assert c.get("/healthz").status_code == 200  # Kubernetes must not kill the pod
        assert loaded_service.metrics.registry.get_sample_value("injected_failures_total") == 1


def test_injected_failures_keep_their_route_label(loaded_service):
    """The SLI filters on route=~"/api/.+", so injected 500s must carry the real route."""
    settings = Settings(failure_rate=1.0)
    app = create_app(settings=settings, service=loaded_service, start_background=False)
    with TestClient(app) as c:
        assert c.get("/api/v1/satellites/25544/telemetry").status_code == 500
        assert c.get("/api/v1/does-not-exist").status_code == 500
    registry = loaded_service.metrics.registry
    labels = {"method": "GET", "route": "/api/v1/satellites/{norad_id}/telemetry", "status": "500"}
    assert registry.get_sample_value("http_requests_total", labels) == 1
    unknown = {"method": "GET", "route": "unmatched", "status": "500"}
    assert registry.get_sample_value("http_requests_total", unknown) == 1
