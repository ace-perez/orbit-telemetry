"""Client for CelesTrak's GP (orbital elements) API.

Fair-use policy: CelesTrak updates data about every 2 hours and blocks clients that
poll faster. The service caches results and refreshes on `orbit_refresh_seconds`.
"""

from typing import Protocol

import httpx

from orbit_telemetry import __version__


class CelesTrakError(Exception):
    """CelesTrak could not supply valid elements for a satellite."""


class ElementsSource(Protocol):
    """Anything that can return one OMM record for a NORAD ID (real client or test fake)."""

    async def fetch(self, norad_id: int) -> dict: ...


class CelesTrakClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient) -> None:
        self._url = f"{base_url.rstrip('/')}/NORAD/elements/gp.php"
        self._client = client

    async def fetch(self, norad_id: int) -> dict:
        try:
            response = await self._client.get(
                self._url,
                params={"CATNR": norad_id, "FORMAT": "json"},
                headers={"User-Agent": f"orbit-telemetry/{__version__}"},
                timeout=10.0,  # never hang a refresh on a slow upstream
            )
            response.raise_for_status()
            records = response.json()
        except httpx.HTTPError as exc:
            raise CelesTrakError(f"request for {norad_id} failed: {exc}") from exc
        except ValueError as exc:  # CelesTrak answers unknown IDs with plain text
            raise CelesTrakError(f"non-JSON response for {norad_id}") from exc

        if not isinstance(records, list) or not records:
            raise CelesTrakError(f"no elements returned for {norad_id}")
        return records[0]
