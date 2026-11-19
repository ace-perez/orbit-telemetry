"""CelesTrak client against a mocked HTTP transport (no real network)."""

import asyncio

import httpx
import pytest

from orbit_telemetry.celestrak import CelesTrakClient, CelesTrakError


def fetch_with(handler, norad_id=25544):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await CelesTrakClient("https://example.test/", http).fetch(norad_id)

    return asyncio.run(run())


def test_requests_one_satellite_as_json(omm_records):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = request.url
        seen["agent"] = request.headers["user-agent"]
        return httpx.Response(200, json=[omm_records[25544]])

    record = fetch_with(handler)
    assert record["NORAD_CAT_ID"] == 25544
    assert seen["url"].path == "/NORAD/elements/gp.php"
    assert seen["url"].params["CATNR"] == "25544"
    assert seen["url"].params["FORMAT"] == "json"
    assert seen["agent"].startswith("orbit-telemetry/")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(403, text="Forbidden"),  # rate-limited or blocked
        httpx.Response(200, text="No GP data found"),  # unknown satellite
        httpx.Response(200, json=[]),  # empty result
    ],
)
def test_bad_responses_raise_celestrak_error(response):
    with pytest.raises(CelesTrakError):
        fetch_with(lambda request: response)


def test_network_errors_raise_celestrak_error():
    def handler(request):
        raise httpx.ConnectError("unreachable")

    with pytest.raises(CelesTrakError):
        fetch_with(handler)
