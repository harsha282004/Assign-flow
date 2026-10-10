"""GET /api/v1/health: real PostgreSQL, Redis and MinIO connectivity (unchanged Phase 1 behaviour)."""

import asyncio
import logging

import httpx
import psycopg
import redis
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.config import Settings

logger = logging.getLogger("assignflow")
router = APIRouter(tags=["health"])


def _check_db(settings: Settings) -> None:
    # DATABASE_URL uses the SQLAlchemy dialect form (postgresql+psycopg://); psycopg wants plain libpq.
    dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(dsn, connect_timeout=max(1, int(settings.health_timeout_seconds))) as conn:
        conn.execute("SELECT 1")


def _check_redis(settings: Settings) -> None:
    client = redis.Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=settings.health_timeout_seconds,
        socket_timeout=settings.health_timeout_seconds,
    )
    try:
        client.ping()
    finally:
        client.close()


def _check_storage(settings: Settings) -> None:
    # MinIO liveness endpoint; works without credentials and without the bucket existing.
    url = settings.s3_endpoint_url.rstrip("/") + "/minio/health/live"
    with httpx.Client(timeout=settings.health_timeout_seconds) as client:
        client.get(url).raise_for_status()


async def _probe(name: str, fn, settings: Settings) -> str:
    try:
        await asyncio.to_thread(fn, settings)
        return "ok"
    except Exception as exc:  # noqa: BLE001 - report any failure as "down"
        # Log only the dependency and error category; never the message (may embed credentials).
        logger.warning("health: %s check failed (%s)", name, type(exc).__name__)
        return "down"


@router.get("/health")
async def health(request: Request) -> JSONResponse:
    settings: Settings = request.app.state.settings
    db, rd, storage = await asyncio.gather(
        _probe("db", _check_db, settings),
        _probe("redis", _check_redis, settings),
        _probe("storage", _check_storage, settings),
    )
    healthy = db == rd == storage == "ok"
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ok" if healthy else "degraded", "db": db, "redis": rd, "storage": storage},
    )
