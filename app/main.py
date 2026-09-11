"""
PrepLink FastAPI Application
=============================
Single-process API. Per ADR-004 there is no Celery worker fleet — each
recipe request runs the AI pipeline synchronously in-process and returns the
finished result in the same HTTP response (PRD <15s P95 cart-build budget).
Redis is used only as a cache (rate limiting, recipe-by-id storage).
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import cart_router, recipe_router
from app.core.cache import recipe_cache
from app.core.config import settings
from app.core.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("PrepLink API starting")
    try:
        await recipe_cache.ping()
        logger.info("Redis connected (cache)")
    except Exception:
        logger.warning("Redis unavailable — cache falling back to in-memory dict")
    yield
    logger.info("PrepLink API shutting down")
    await recipe_cache.close()


app = FastAPI(
    title="PrepLink API",
    version="3.0.0",
    description=(
        "Social recipe URLs → age-adapted, pantry-aware Instacart carts.\n\n"
        "Each request runs the AI pipeline synchronously and returns the "
        "finished recipe + cart in the same response — see ARCHITECTURE.md "
        "and ADR-004."
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


@app.get("/health", tags=["System"])
async def health():
    cache_ok = await recipe_cache.ping()

    return {
        "status":      "ok" if cache_ok else "degraded",
        "version":     "3.0.0",
        "environment": settings.ENVIRONMENT,
        "redis_cache": "ok" if cache_ok else "down",
    }


# Local-preview UI (static pages). Mounted last so it only catches paths not
# already claimed by the API routes above. There is no real Next.js
# frontend/ app yet (see ARCHITECTURE.md) — this is a stand-in until one exists.
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
