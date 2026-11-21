"""The console page: served by the app, locked down by headers, built only from local files."""

import hashlib
import re
from pathlib import Path

import pytest

from orbit_telemetry.main import STATIC_DIR

VENDOR = STATIC_DIR / "vendor"


def test_page_is_served_with_strict_security_headers(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    csp = response.headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "Orbit Telemetry" in response.text


@pytest.mark.parametrize(
    ("path", "content_type"),
    [
        ("/static/app.js", "javascript"),
        ("/static/styles.css", "text/css"),
        ("/static/vendor/d3.min.js", "javascript"),
        ("/static/vendor/land-110m.json", "application/json"),
        ("/static/vendor/fonts/inter-latin-400-normal.woff2", "font/woff2"),
    ],
)
def test_static_files_are_served_with_the_same_headers(client, path, content_type):
    response = client.get(path)
    assert response.status_code == 200
    assert content_type in response.headers["content-type"]
    assert "content-security-policy" in response.headers


def test_api_docs_keep_working_without_the_page_policy(client):
    """Swagger UI loads its scripts from a CDN, so the strict policy must not reach /docs."""
    response = client.get("/docs")
    assert response.status_code == 200
    assert "content-security-policy" not in response.headers
    assert "content-security-policy" not in client.get("/api/v1/info").headers


def test_page_routes_are_labelled_in_metrics(client):
    client.get("/")
    client.get("/static/app.js")
    client.get("/static/missing.js")
    text = client.get("/metrics").text
    assert 'route="/",status="200"' in text
    assert 'route="/static",status="200"' in text
    assert 'route="/static",status="404"' in text


def test_page_loads_nothing_from_other_sites():
    """No CDN at runtime: every src, href and url() in the page's own files is local."""
    for name in ("index.html", "styles.css", "app.js"):
        text = (STATIC_DIR / name).read_text()
        assert not re.search(r"""(src|href)\s*=\s*["']?(https?:)?//""", text), name
        assert not re.search(r"""url\(\s*["']?(https?:)?//""", text), name
        assert not re.search(r"\.innerHTML|outerHTML|insertAdjacentHTML|document\.write", text), (
            name
        )


def test_vendored_files_match_the_manifest():
    """Every vendored file is byte-for-byte what SHA256SUMS records, and nothing is unlisted."""
    listed = {}
    for line in (VENDOR / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split(maxsplit=1)
        listed[name] = digest
    for name, digest in listed.items():
        actual = hashlib.sha256((VENDOR / name).read_bytes()).hexdigest()
        assert actual == digest, f"{name} changed: update VENDOR.md and SHA256SUMS on purpose"

    shipped = {
        str(p.relative_to(VENDOR))
        for p in VENDOR.rglob("*")
        if p.is_file() and p.suffix in {".js", ".json", ".woff2"}
    }
    assert shipped == set(listed), "a vendored file is missing from SHA256SUMS"


def test_static_dir_ships_inside_the_package():
    """The files live in the package, so the wheel and the image carry them automatically."""
    assert STATIC_DIR.is_dir()
    assert Path(STATIC_DIR, "index.html").is_file()
