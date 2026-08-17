"""
Pytest configuration and shared fixtures for all tests.

Strategy:
- Use SQLite in-memory database (aiosqlite driver) so tests run without
  a real PostgreSQL instance. This works because we use SQLAlchemy ORM
  which abstracts the DB dialect for these test cases.
- Each test gets a fresh database via function-scoped fixtures, so tests
  are fully isolated and can run in any order.
- We override the FastAPI get_db dependency to inject the test session.
- We create all tables from the ORM metadata before each test.

Note on PostgreSQL-specific types:
- JSONB and INET columns are used in AuditLog. SQLite stores JSONB as
  TEXT and INET as TEXT, which is fine for testing logic.
  The schema migration (Alembic) handles the real PG types.
"""
import asyncio
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database import Base, get_db
from app.main import create_application
from app.models import user as user_models  # noqa — ensure models are imported
from app.models import product as product_models  # noqa
from app.models import inventory as inventory_models  # noqa
from app.models import purchase_request as pr_models  # noqa
from app.models import notification as notif_models  # noqa
from app.models import audit_log as audit_models  # noqa
from app.utils.security import hash_password, create_access_token

# ---------------------------------------------------------------------------
# Event loop — use a single loop for the entire test session
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# In-memory database engine (function-scoped = new DB per test)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db_engine():
    """Create a fresh SQLite in-memory engine for each test."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a test database session."""
    session_factory = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    async with session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Seed roles and test users
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def seeded_roles(db_session: AsyncSession):
    """Insert the three application roles."""
    from app.models.user import Role
    roles = {}
    for name in ("ADMIN", "MANAGER", "STAFF"):
        role = Role(id=uuid.uuid4(), name=name, description=name)
        db_session.add(role)
        roles[name] = role
    await db_session.commit()
    return roles


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession, seeded_roles):
    from app.models.user import User
    user = User(
        id=uuid.uuid4(),
        email="admin@test.com",
        username="admin",
        hashed_password=hash_password("Admin123!"),
        full_name="Test Admin",
        role_id=seeded_roles["ADMIN"].id,
    )
    db_session.add(user)
    await db_session.commit()
    # Attach role for hasattr access in service
    user.role = seeded_roles["ADMIN"]
    return user


@pytest_asyncio.fixture
async def manager_user(db_session: AsyncSession, seeded_roles):
    from app.models.user import User
    user = User(
        id=uuid.uuid4(),
        email="manager@test.com",
        username="manager",
        hashed_password=hash_password("Manager123!"),
        full_name="Test Manager",
        role_id=seeded_roles["MANAGER"].id,
    )
    db_session.add(user)
    await db_session.commit()
    user.role = seeded_roles["MANAGER"]
    return user


@pytest_asyncio.fixture
async def staff_user(db_session: AsyncSession, seeded_roles):
    from app.models.user import User
    user = User(
        id=uuid.uuid4(),
        email="staff@test.com",
        username="staff",
        hashed_password=hash_password("Staff123!"),
        full_name="Test Staff",
        role_id=seeded_roles["STAFF"].id,
    )
    db_session.add(user)
    await db_session.commit()
    user.role = seeded_roles["STAFF"]
    return user


# ---------------------------------------------------------------------------
# FastAPI test client with DB override
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    """
    HTTP test client with the DB dependency overridden to use the
    in-memory test session.
    """
    app = create_application()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Auth token helpers
# ---------------------------------------------------------------------------

def make_token(user_id: str, role: str) -> str:
    return create_access_token(user_id=user_id, role=role)


def auth_headers(user_id: str, role: str) -> dict:
    return {"Authorization": f"Bearer {make_token(user_id, role)}"}
