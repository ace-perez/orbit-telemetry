"""FastAPI application: routes, middleware and lifecycle.

Run locally with `uv run orbit-telemetry`, then open http://localhost:8000/docs.
"""

import asyncio
import contextlib
import logging
import random
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated

import httpx
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from orbit_telemetry import schemas
from orbit_telemetry.celestrak import CelesTrakClient
from orbit_telemetry.config import Settings
from orbit_telemetry.logging_config import configure_logging
from orbit_telemetry.metrics import Metrics
from orbit_telemetry.service import TelemetryService
from orbit_telemetry.sun import subsolar_point

log = logging.getLogger("orbit_telemetry.access")


def create_app(
    settings: Settings | None = None,
    service: TelemetryService | None = None,
    start_background: bool = True,
) -> FastAPI:
    """Build the app. Tests inject a service with a fake data source and a fixed clock."""
    settings = settings or Settings()
    configure_logging(settings.log_level)

    http_client: httpx.AsyncClient | None = None
    if service is None:
        http_client = httpx.AsyncClient()
        service = TelemetryService(
            settings=settings,
            source=CelesTrakClient(settings.celestrak_base_url, http_client),
            metrics=Metrics(),
        )
    metrics = service.metrics
    metrics.build_info.labels(version=settings.app_version).set(1)
    # Not a security control: picks which requests to fail in the demo.
    failure_rng = random.Random()  # nosec B311

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(service.run_forever()) if start_background else None
        yield
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if http_client:
            await http_client.aclose()

    app = FastAPI(
        title="Orbit Telemetry API",
        version=settings.app_version,
        description="Real orbits from CelesTrak, simulated spacecraft subsystems.",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def observe(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Request ID, failure injection, RED metrics and one structured log line."""
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        start = time.perf_counter()

        if request.url.path.startswith("/api/") and failure_rng.random() < settings.failure_rate:
            metrics.injected_failures.inc()
            response: Response = JSONResponse({"detail": "injected failure"}, status_code=500)
        else:
            response = await call_next(request)

        duration = time.perf_counter() - start
        route = request.scope.get("route")
        # Label by route TEMPLATE (/satellites/{norad_id}) not raw path, to keep cardinality low.
        route_label = getattr(route, "path", "unmatched")
        metrics.http_requests.labels(request.method, route_label, str(response.status_code)).inc()
        metrics.http_duration.labels(request.method, route_label).observe(duration)
        response.headers["x-request-id"] = request_id
        log.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "route": route_label,
                "status": response.status_code,
                "duration_ms": round(duration * 1000, 2),
            },
        )
        return response

    # -- probes and metrics --------------------------------------------------------

    @app.get("/healthz", tags=["ops"])
    def healthz() -> dict[str, str]:
        """Liveness: the process is up. Kubernetes restarts the pod if this fails."""
        return {"status": "ok"}

    @app.get("/readyz", tags=["ops"])
    def readyz() -> JSONResponse:
        """Readiness: every satellite has data. Kubernetes only routes traffic when ready."""
        if service.ready:
            return JSONResponse({"status": "ready"})
        return JSONResponse(
            {
                "status": "starting",
                "ready": service.ready_count,
                "expected": len(settings.norad_ids),
            },
            status_code=503,
        )

    @app.get("/metrics", tags=["ops"], include_in_schema=False)
    def metrics_endpoint() -> Response:
        return Response(generate_latest(metrics.registry), media_type=CONTENT_TYPE_LATEST)

    # -- API -----------------------------------------------------------------------

    def snapshot_or_error(norad_id: int) -> schemas.Telemetry:
        if norad_id not in settings.norad_ids:
            raise HTTPException(status_code=404, detail=f"satellite {norad_id} is not tracked")
        snapshot = service.snapshots.get(norad_id)
        if snapshot is None:
            raise HTTPException(status_code=503, detail="orbital data not loaded yet")
        return snapshot

    @app.get("/api/v1/info", response_model=schemas.Info, tags=["api"])
    def info() -> schemas.Info:
        return schemas.Info(
            version=settings.app_version,
            environment=settings.environment,
            satellites_tracked=len(settings.norad_ids),
            satellites_ready=service.ready_count,
            orbital_data_ok=service.orbital_data_ok(service.clock()),
            refresh_interval_seconds=settings.orbit_refresh_seconds,
            tick_seconds=settings.tick_seconds,
        )

    @app.get("/api/v1/satellites", response_model=list[schemas.SatelliteSummary], tags=["api"])
    def satellites() -> list[schemas.SatelliteSummary]:
        return [
            schemas.SatelliteSummary(
                norad_id=s.norad_id,
                name=s.name,
                orbit_class=s.orbit_class,
                inclination_deg=s.inclination_deg,
                altitude_km=s.position.altitude_km,
                sunlit=s.power.sunlit,
            )
            for nid in settings.norad_ids
            if (s := service.snapshots.get(nid))
        ]

    @app.get(
        "/api/v1/satellites/{norad_id}/telemetry", response_model=schemas.Telemetry, tags=["api"]
    )
    def telemetry(norad_id: int) -> schemas.Telemetry:
        return snapshot_or_error(norad_id)

    @app.get("/api/v1/satellites/{norad_id}/track", response_model=schemas.Track, tags=["api"])
    def track(
        norad_id: int,
        orbits: Annotated[int, Query(ge=1, le=3)] = 3,
        step_seconds: Annotated[int, Query(ge=10, le=300)] = 60,
    ) -> schemas.Track:
        """Ground track for the next `orbits` revolutions (passes 0, +1, +2 on the globe)."""
        snapshot_or_error(norad_id)
        points = service.propagator.ground_track(
            service.elements[norad_id], service.clock(), orbits, step_seconds
        )
        return schemas.Track(
            norad_id=norad_id,
            orbits=orbits,
            step_seconds=step_seconds,
            points=[
                schemas.TrackPoint(
                    time=p.time,
                    latitude_deg=round(p.latitude_deg, 3),
                    longitude_deg=round(p.longitude_deg, 3),
                )
                for p in points
            ],
        )

    @app.get("/api/v1/sun", response_model=schemas.Sun, tags=["api"])
    def sun() -> schemas.Sun:
        """Subsolar point; the globe draws the day/night terminator 90 degrees from it."""
        now = service.clock()
        latitude, longitude = subsolar_point(now)
        return schemas.Sun(
            time=now,
            subsolar_latitude_deg=round(latitude, 3),
            subsolar_longitude_deg=round(longitude, 3),
        )

    return app
