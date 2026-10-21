"""DOUMITT Agricultural ERP - FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from fastapi_cache.backends.redis import RedisBackend
from redis import asyncio as aioredis
from slowapi.middleware import SlowAPIMiddleware

from auth import limiter
from config import settings
from exceptions import register_exception_handlers
from routers import auth_router, expenses, invoices, projects, reports, warehouse

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("doumitt")

BASE_DIR = Path(__file__).resolve().parent

if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise the report cache, with a safe in-memory fallback."""
    redis_client = None
    if settings.cache_enabled:
        try:
            redis_client = aioredis.from_url(settings.redis_url)
            await redis_client.ping()
            FastAPICache.init(RedisBackend(redis_client), prefix="doumitt")
            logger.info("Report cache connected to Redis")
        except Exception:
            logger.warning("Redis unavailable - falling back to in-memory report cache")
            if redis_client is not None:
                try:
                    await redis_client.aclose()
                except Exception:
                    pass
                redis_client = None
            FastAPICache.init(InMemoryBackend(), prefix="doumitt")
    yield
    if redis_client is not None:
        try:
            await redis_client.aclose()
        except Exception:
            pass


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "نظام ERP زراعي سحابي متعدد المستأجرين لإدارة المشاريع والبيوت البلاستيكية، "
        "المستودع المركزي وجرد الصيدليات، الشغّيلة بالحصة، المصاريف بعملتين، "
        "وفواتير سوق الخضرة مع حسابات تكلفة وربحية دقيقة لكل بيت."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.middleware("http")
async def no_store_api_responses(request: Request, call_next):
    """Authenticated API data must never be cached by browsers or proxies.

    Server-side report caching stays active; only HTTP response caching is
    disabled so a logout/login on the same browser can never show another
    tenant's cached JSON.
    """
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Pragma"] = "no-cache"
    return response
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(auth_router.router)
app.include_router(projects.router)
app.include_router(warehouse.router)
app.include_router(expenses.router)
app.include_router(invoices.router)
app.include_router(reports.router)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.get("/", include_in_schema=False)
async def dashboard(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"app_name": settings.app_name, "app_version": settings.app_version},
    )


@app.get("/health", tags=["System"], summary="فحص صحة الخدمة")
async def health() -> dict:
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }
