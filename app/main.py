"""
PrepLink FastAPI Application
=============================
API process only — no background threads, no APScheduler.
All heavy work is dispatched to the Celery worker fleet via Redis.

Process topology (see docker-compose.yml):
  api              → FastAPI (this file)  — port 8000
  worker-interactive → Celery worker      — queue: interactive  concurrency: 4
  worker-batch       → Celery worker      — queue: batch        concurrency: 8
  beat               → Celery beat        — periodic tasks      (RedBeat scheduler)
  flower             → Celery flower      — monitoring UI       port 5555
  redis              → Redis              — broker + cache + result-backend
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import batch_router, cart_router, recipe_router, ws_router
from app.core.cache import recipe_cache
from app.core.config import settings
from app.core.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("PrepLink API starting — Celery worker fleet handles background tasks")
    try:
        await recipe_cache.ping()
        logger.info("Redis connected (DB 0 — cache)")
    except Exception:
        logger.warning("Redis unavailable — cache falling back to in-memory dict")
    yield
    logger.info("PrepLink API shutting down")
    await recipe_cache.close()


app = FastAPI(
    title="PrepLink API",
    version="2.0.0",
    description=(
        "Social recipe URLs → age-adapted, pantry-aware Instacart carts.\n\n"
        "**Pipeline:**\n"
        "- Interactive queue (`queue=interactive`): real-time, standard API quota, user is waiting\n"
        "- Batch queue (`queue=batch`): 50% cheaper, separate quota pool, up to 24h SLA\n\n"
        "Background processing runs in dedicated Celery workers (not in this process)."
    ),
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
)

if settings.ENVIRONMENT == "production":
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["*.preplink.app", "preplink.app"],
    )


@app.middleware("http")
async def timing_header(request: Request, call_next):
    t0 = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Response-Time-Ms"] = str(int((time.perf_counter() - t0) * 1000))
    return response


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if request.url.path.startswith("/api/recipe/process"):
        ip  = request.client.host if request.client else "unknown"
        key = f"rl:{ip}:{int(time.time() // 60)}"
        cnt = await recipe_cache.incr(key)
        if cnt == 1:
            await recipe_cache.expire(key, 60)
        if cnt > settings.RATE_LIMIT_PER_MINUTE:
            return JSONResponse(
                status_code=429,
                content={"detail": f"Rate limit: {settings.RATE_LIMIT_PER_MINUTE} req/min"},
            )
    return await call_next(request)


app.include_router(recipe_router)
app.include_router(cart_router)
app.include_router(batch_router)
app.include_router(ws_router)


@app.get("/health", tags=["System"])
async def health():
    cache_ok = await recipe_cache.ping()

    # Check Celery broker reachability
    broker_ok = False
    try:
        import redis
        r = redis.from_url(settings.CELERY_BROKER_URL, socket_timeout=2)
        r.ping()
        broker_ok = True
    except Exception:
        pass

    return {
        "status":       "ok" if (cache_ok and broker_ok) else "degraded",
        "version":      "2.0.0",
        "environment":  settings.ENVIRONMENT,
        "redis_cache":  "ok" if cache_ok  else "down",
        "celery_broker":"ok" if broker_ok else "down",
        "pipelines":    ["interactive (queue=interactive)", "batch (queue=batch, 50% cost)"],
        "worker_docs":  "http://localhost:5555",
    }


# Local-preview UI (single static page). Mounted last so it only catches
# paths not already claimed by the API routes above. There is no real
# frontend/ app yet (see ADR-003) — this is a stand-in until one exists.
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
