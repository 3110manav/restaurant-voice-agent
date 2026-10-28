# syntax=docker/dockerfile:1
# The realtime voice worker, hosted on LiveKit Cloud (`lk agent create` / `lk agent deploy`).
# Built from the staged folder that deploy.sh prepares: this file, requirements.txt and app/.
# Follows LiveKit's Python template: a glibc slim base, a non-root user, and the worker started with
# the `start` subcommand. LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET are injected by LiveKit
# Cloud; every other secret comes from secrets.env (never copied into the image).
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

FROM base AS build
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ python3-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN python -m venv .venv
ENV PATH="/app/.venv/bin:$PATH"
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ app/

FROM base
ARG UID=10001
RUN adduser --disabled-password --gecos "" --home "/app" --shell "/sbin/nologin" --uid "${UID}" appuser
WORKDIR /app
COPY --from=build --chown=appuser:appuser /app /app
ENV PATH="/app/.venv/bin:$PATH"
USER appuser
CMD ["python", "-m", "app.voice.livekit_worker", "start"]
