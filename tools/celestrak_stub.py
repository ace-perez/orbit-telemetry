"""A tiny stand-in for CelesTrak's GP API, serving the test fixtures.

Used for local development without hitting CelesTrak (fair use), and in Phase 4 as the
fake upstream for integration tests in Docker Compose. Standard library only.

    uv run python tools/celestrak_stub.py            # serves on port 8081
    CELESTRAK_BASE_URL=http://localhost:8081 uv run orbit-telemetry
"""

import json
import os
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "omm.json"
RECORDS = json.loads(FIXTURE.read_text())
# Re-stamp the epoch to "now" so propagation stays accurate however old the fixture is.
NOW = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000000")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (name required by BaseHTTPRequestHandler)
        url = urlparse(self.path)
        if url.path == "/healthz":
            return self._send(200, "text/plain", b"ok")
        if url.path != "/NORAD/elements/gp.php":
            return self._send(404, "text/plain", b"not found")
        catnr = parse_qs(url.query).get("CATNR", [""])[0]
        record = RECORDS.get(catnr)
        if record is None:
            return self._send(200, "text/plain", b"No GP data found")  # mimics CelesTrak
        body = json.dumps([{**record, "EPOCH": NOW}]).encode()
        return self._send(200, "application/json", body)

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    port = int(os.environ.get("STUB_PORT", "8081"))
    print(f"CelesTrak stub listening on :{port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()  # nosec B104
