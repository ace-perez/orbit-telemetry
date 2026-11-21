# syntax=docker/dockerfile:1
#
# Multi-stage build.
#   builder: has uv, installs the locked dependencies and the app into /app/.venv
#   runtime: a clean Python image with only that virtual environment, run as a non-root user
# Nothing used to build the image (uv, caches, source tree, tests) ends up in the final layer.

# Exact patch versions, so a rebuild next month gets the same base. Dependabot proposes updates.
ARG PYTHON_IMAGE=python:3.13.18-slim-trixie
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.9

FROM ${UV_IMAGE} AS uv

# ---------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS builder

COPY --from=uv /uv /usr/local/bin/uv

# UV_COMPILE_BYTECODE: precompile .pyc files so the container starts faster.
# UV_LINK_MODE=copy: the cache is a separate mount, so copy files instead of hard-linking.
# UV_PYTHON_DOWNLOADS=never: use the image's Python, never download another one.
# UV_PROJECT_ENVIRONMENT: where the virtual environment is created.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# 1) Dependencies only. This layer is reused from cache until uv.lock or pyproject.toml change,
#    so editing application code does not reinstall FastAPI, Skyfield and the rest.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project

# 2) The application itself, installed as a normal (non-editable) package.
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# ---------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS runtime

# Set by CI to the release version or commit; shown in /api/v1/info and the build_info metric.
ARG APP_VERSION=dev

LABEL org.opencontainers.image.title="orbit-telemetry" \
      org.opencontainers.image.description="Satellite telemetry API: real orbits from CelesTrak, simulated subsystems" \
      org.opencontainers.image.source="https://github.com/ace-perez/orbit-telemetry" \
      org.opencontainers.image.licenses="MIT"

# Base image hardening, run as root before switching user. Found by the Trivy image scan:
# - zlib1g: CVE-2026-85091 (HIGH) is fixed in Debian's update deb13u1, which this base image
#   does not include yet. Remove the pinned upgrade once Dependabot moves to a base image built
#   after the fix (otherwise apt would be asked to downgrade and the build fails, as a reminder).
# - pip: not needed at runtime, because uv installed everything in the builder stage. Removing
#   it drops the urllib3, msgpack and setuptools code pip bundles (5 HIGH findings) and means
#   nothing can be pip-installed inside a running container.
# Then a fixed, unprivileged user. A numeric UID lets Kubernetes verify runAsNonRoot (Phase 5).
RUN apt-get update \
    && apt-get install --yes --no-install-recommends --only-upgrade \
        "zlib1g=1:1.3.dfsg+really1.3.1-1+deb13u1" \
        "libc6=2.41-12+deb13u5" \
        "libc-bin=2.41-12+deb13u5" \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip uninstall --yes pip \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

# Owned by root and read-only to the app user: the running process cannot modify its own code.
COPY --from=builder /app/.venv /app/.venv

# HOST=0.0.0.0: inside a container the app must listen on all interfaces to be reachable
# through the container network. The code's default stays 127.0.0.1 (Bandit B104).
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    APP_VERSION=${APP_VERSION}

USER 10001:10001
WORKDIR /app
EXPOSE 8000

# Used by Docker and Compose. Kubernetes ignores it and uses the probes in the Helm chart.
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"]

# Exec form: the app is PID 1 and receives SIGTERM directly, so shutdowns are clean.
CMD ["orbit-telemetry"]
