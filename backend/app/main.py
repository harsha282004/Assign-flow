"""AssignFlow API application factory (Phase 3: health + authentication)."""

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

import redis
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.security import require_jwt_secret
from app.core.upload_limit import UploadSizeLimitMiddleware
from app.routers import auth, faculty, files, health, notifications, student
from app.services import reminders
from app.services.ratelimit import limiter
from app.services.storage import make_s3_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # one INFO line per health probe is noise
request_logger = logging.getLogger("assignflow.request")

API_PREFIX = "/api/v1"


def create_app(settings: Settings) -> FastAPI:
    require_jwt_secret(settings)  # fail fast with a clear message if the signing secret is weak/missing

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(reminders.scheduler_loop()) if settings.reminder_scheduler_enabled else None
        yield
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        app.state.redis.close()

    app = FastAPI(title="AssignFlow API", version="0.7.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.limiter = limiter
    # Short timeouts: when Redis is down we fail closed quickly instead of hanging requests.
    app.state.redis = redis.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )

    # Added before CORS so that CORS is the outer layer and rejected uploads still carry CORS headers.
    app.state.s3 = make_s3_client(settings)

    app.add_middleware(UploadSizeLimitMiddleware, max_file_mb=settings.max_upload_mb)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["Retry-After", "Content-Disposition"],
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):  # method, path, status, duration, user UUID only
        started = time.perf_counter()
        response = await call_next(request)
        request_logger.info(
            "%s %s -> %d (%.0f ms) user=%s",
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - started) * 1000,
            getattr(request.state, "user_id", "-"),
        )
        return response

    register_error_handlers(app)
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(faculty.router, prefix=API_PREFIX)
    app.include_router(student.router, prefix=API_PREFIX)
    app.include_router(files.router, prefix=API_PREFIX)
    app.include_router(notifications.router, prefix=API_PREFIX)
    return app


app = create_app(get_settings())
