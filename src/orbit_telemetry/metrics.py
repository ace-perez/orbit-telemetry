"""Prometheus metrics.

Two kinds, both scraped from /metrics:
- RED metrics for the API itself (Rate, Errors, Duration): what SLOs and alerts use.
- Domain gauges for each satellite: what the Grafana telemetry dashboard shows.

Each app instance owns its registry, so tests can create many apps without clashes.
"""

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

SATELLITE_LABELS = ("norad_id", "name")


class Metrics:
    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        self.registry = registry or CollectorRegistry()
        r = self.registry

        self.http_requests = Counter(
            "http_requests_total",
            "HTTP requests handled, by route template and status code.",
            ("method", "route", "status"),
            registry=r,
        )
        self.http_duration = Histogram(
            "http_request_duration_seconds",
            "HTTP request latency, by route template.",
            ("method", "route"),
            registry=r,
        )
        self.injected_failures = Counter(
            "injected_failures_total",
            "Requests deliberately failed by FAILURE_RATE (rollback demo).",
            registry=r,
        )
        self.build_info = Gauge(
            "orbit_telemetry_build_info",
            "Always 1; labels carry build data.",
            ("version",),
            registry=r,
        )

        self.altitude = Gauge(
            "satellite_altitude_km",
            "Altitude above the WGS-84 ellipsoid.",
            SATELLITE_LABELS,
            registry=r,
        )
        self.sunlit = Gauge(
            "satellite_sunlit",
            "1 in sunlight, 0 in Earth's shadow.",
            SATELLITE_LABELS,
            registry=r,
        )
        self.battery_voltage = Gauge(
            "satellite_battery_voltage_volts",
            "Simulated main bus voltage.",
            SATELLITE_LABELS,
            registry=r,
        )
        self.state_of_charge = Gauge(
            "satellite_battery_soc_percent",
            "Simulated battery state of charge.",
            SATELLITE_LABELS,
            registry=r,
        )
        self.solar_current = Gauge(
            "satellite_solar_array_current_amperes",
            "Simulated solar array output.",
            SATELLITE_LABELS,
            registry=r,
        )
        self.temperature = Gauge(
            "satellite_core_temperature_celsius",
            "Simulated core temperature.",
            SATELLITE_LABELS,
            registry=r,
        )
        self.orbital_data_age = Gauge(
            "orbital_data_age_seconds",
            "Seconds since orbital elements were last fetched successfully.",
            SATELLITE_LABELS,
            registry=r,
        )
        self.fetch_failures = Counter(
            "celestrak_fetch_failures_total",
            "Failed CelesTrak fetches.",
            ("norad_id",),
            registry=r,
        )
