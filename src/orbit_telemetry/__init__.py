"""Orbit Telemetry: real orbits from CelesTrak, simulated spacecraft subsystems."""

__version__ = "0.1.0"


def main() -> None:
    """Entry point for `uv run orbit-telemetry`: serve the API with uvicorn."""
    import uvicorn

    from orbit_telemetry.config import Settings

    settings = Settings()
    uvicorn.run(
        "orbit_telemetry.main:create_app",
        factory=True,  # call create_app() to build the app
        host=settings.host,
        port=settings.port,
        access_log=False,  # our middleware writes structured access logs instead
    )
