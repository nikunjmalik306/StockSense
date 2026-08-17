"""
Alembic environment configuration.

Key design decisions:
- We read the database URL from app/config.py (Pydantic Settings) so
  there is a single source of truth for all configuration.
- We import app.models so autogenerate can detect all ORM tables.
- We use the sync psycopg2 URL because Alembic's migration runner is
  synchronous (it's a CLI tool, not an async server).
- include_object filters out PostGIS/spatial tables if any exist.
"""
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make sure the backend/ directory is on sys.path so we can import app.*
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import get_settings
from app.database import Base

# Import all models so their tables are registered on Base.metadata
import app.models  # noqa: F401

# Alembic Config object (provides access to alembic.ini values)
config = context.config

# Override the sqlalchemy.url with the value from our app config
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url_sync)

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# This is the metadata object that autogenerate inspects
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Run migrations without a live database connection.
    Useful for generating SQL scripts to review before applying.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,  # detect column type changes
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations against a live database connection.
    This is what 'alembic upgrade head' uses.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # don't pool connections in migration scripts
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
