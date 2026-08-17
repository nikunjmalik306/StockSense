"""
StockSense FastAPI application factory.

This module creates and configures the FastAPI app instance.
Routers are registered here as they are built in subsequent blocks.
"""
import logging
import logging.config

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.middleware.logging import RequestLoggingMiddleware

settings = get_settings()


# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
# Simple dict-based logging config. In production you would ship logs to
# a collector (Datadog, CloudWatch, etc.) but for a portfolio project
# structured stdout logs are the right level of complexity.

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            "datefmt": "%Y-%m-%dT%H:%M:%S",
        },
        "access": {
            "format": (
                "%(asctime)s [ACCESS] %(message)s "
                "| method=%(method)s path=%(path)s "
                "status=%(status_code)s duration=%(duration_ms)sms "
                "request_id=%(request_id)s"
            ),
            "datefmt": "%Y-%m-%dT%H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
        },
        "access_console": {
            "class": "logging.StreamHandler",
            "formatter": "access",
        },
    },
    "loggers": {
        "stocksense": {
            "handlers": ["console"],
            "level": settings.log_level,
            "propagate": False,
        },
        "stocksense.access": {
            "handlers": ["access_console"],
            "level": "INFO",
            "propagate": False,
        },
        # Suppress noisy SQLAlchemy engine logs in production
        "sqlalchemy.engine": {
            "handlers": ["console"],
            "level": "INFO" if settings.is_development else "WARNING",
            "propagate": False,
        },
    },
    "root": {
        "handlers": ["console"],
        "level": settings.log_level,
    },
}

logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger("stocksense")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_application() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Separating creation into a factory function makes it easy to create
    a test app instance with different settings in the test suite.
    """
    application = FastAPI(
        title="StockSense API",
        description=(
            "Inventory Intelligence & Waste Prevention Platform. "
            "Provides inventory management, risk scoring, ML forecasting, "
            "and a GenAI Inventory Copilot."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # -----------------------------------------------------------------------
    # Middleware (order matters — outermost wraps all inner layers)
    # -----------------------------------------------------------------------

    # CORS — must be before request logging so preflight OPTIONS requests
    # get proper CORS headers even if they never reach a route handler
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request logging — attaches request_id and logs every request
    application.add_middleware(RequestLoggingMiddleware)

    # -----------------------------------------------------------------------
    # Routers (registered as each block is completed)
    # -----------------------------------------------------------------------
    from app.routers import auth, categories, suppliers, products, transactions, inventory, analytics, ml  # noqa: F401

    application.include_router(auth.router,          prefix="/api/v1/auth",         tags=["Authentication"])
    application.include_router(categories.router,    prefix="/api/v1/categories",   tags=["Categories"])
    application.include_router(suppliers.router,     prefix="/api/v1/suppliers",    tags=["Suppliers"])
    application.include_router(products.router,      prefix="/api/v1/products",     tags=["Products"])
    application.include_router(transactions.router,  prefix="/api/v1/transactions", tags=["Transactions"])
    application.include_router(inventory.router,     prefix="/api/v1/inventory",    tags=["Inventory"])
    application.include_router(analytics.router,     prefix="/api/v1/analytics",    tags=["Analytics"])
    application.include_router(ml.router,            prefix="/api/v1/ml",           tags=["Machine Learning"])

    # -----------------------------------------------------------------------
    # Global exception handlers
    # -----------------------------------------------------------------------

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """
        Catch-all for unhandled exceptions.
        Returns a consistent error shape instead of FastAPI's default 500 HTML.
        Never exposes internal error details in production.
        """
        logger.exception(
            "Unhandled exception",
            extra={"path": request.url.path, "method": request.method},
        )
        message = str(exc) if settings.is_development else "An internal error occurred."
        return JSONResponse(
            status_code=500,
            content={"detail": message, "code": "INTERNAL_SERVER_ERROR"},
        )

    # -----------------------------------------------------------------------
    # Startup / shutdown events
    # -----------------------------------------------------------------------

    @application.on_event("startup")
    async def on_startup() -> None:
        logger.info(
            f"StockSense starting up | environment={settings.environment} "
            f"| db={settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
        )

    @application.on_event("shutdown")
    async def on_shutdown() -> None:
        logger.info("StockSense shutting down")

    return application


# ---------------------------------------------------------------------------
# Health check — available before auth, useful for Docker health checks
# ---------------------------------------------------------------------------

app = create_application()


@app.get("/health", tags=["Health"], summary="Health check")
async def health_check():
    """
    Returns service health status.
    Used by Docker health checks and monitoring systems.
    Does a lightweight DB ping to verify connectivity.
    """
    from sqlalchemy import text
    from app.database import AsyncSessionLocal
    import redis.asyncio as aioredis

    db_status = "ok"
    redis_status = "ok"

    # Check DB
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception as e:
        logger.warning(f"Health check DB failed: {e}")
        db_status = "unavailable"

    # Check Redis (non-critical — app works without it)
    try:
        r = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
    except Exception as e:
        logger.warning(f"Health check Redis failed: {e}")
        redis_status = "unavailable"

    overall = "ok" if db_status == "ok" else "degraded"

    return {
        "status": overall,
        "services": {
            "database": db_status,
            "redis": redis_status,
        },
        "version": "1.0.0",
    }
