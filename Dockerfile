# syntax=docker/dockerfile:1

# ---- Stage 1: dependency build --------------------------------------------
# The uv image = uv + a pinned Python. This stage is cached as long as
# pyproject.toml / uv.lock are unchanged — code edits only rebuild stage 2.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder
WORKDIR /app

# Manifests FIRST (layer caching): dependencies reinstall only when the
# lockfile changes, not on every code edit.
COPY pyproject.toml uv.lock README.md ./
# --frozen  : install exactly what uv.lock pins — no re-resolution, so the
#             image is byte-for-byte reproducible from the lockfile.
# --no-dev  : pytest/ruff never enter the production image.
RUN uv sync --frozen --no-dev

# ---- Stage 2: minimal runtime ----------------------------------------------
# Same Debian base as stage 1, no uv, no build toolchain.
FROM python:3.13-slim-bookworm
WORKDIR /app

# Non-root by principle: nothing in this service needs uid 0.
RUN groupadd --system app && useradd --system --gid app --create-home app

# The venv from the builder + the application code — nothing else.
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app app ./app
ENV PATH="/app/.venv/bin:$PATH"

# SQLite on a volume: data survives container replacement. This is the
# payoff of the DATABASE_URL env override — zero code changes for containers.
RUN mkdir -p /data && chown app:app /data
ENV DATABASE_URL=sqlite:////data/timetable.db

USER app
EXPOSE 8000

# slim images ship no curl/wget — probe with the stdlib instead.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status == 200 else 1)"]

# 0.0.0.0 (not 127.0.0.1): the container's loopback is not reachable from
# the host port mapping — bind all interfaces inside, map ports outside.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
