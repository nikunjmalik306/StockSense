"""
Database setup — SQLAlchemy 2.x async engine and session factory.

We use async SQLAlchemy (asyncpg driver) for all application queries
so FastAPI can handle concurrent requests without blocking threads.
Alembic uses the sync psycopg2 URL because it runs as a CLI tool,
not an async server.
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

# Create the async engine.
# pool_pre_ping=True: test connections before using them so stale
# connections from the pool don't cause cryptic errors.
engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    echo=settings.is_development,  # log SQL in dev, silent in prod
)

# Session factory — expire_on_commit=False means we can still
# access model attributes after a commit without re-querying.
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy ORM models.
    All models inherit from this so Alembic can auto-detect them.
    """
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides a database session per request.
    The session is automatically closed when the request finishes,
    even if an exception is raised.

    Usage:
        @router.get("/example")
        async def my_route(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
