"""Async SQLAlchemy engine and session management.

Cloud providers hand out slightly different PostgreSQL URLs (``postgres://``,
``sslmode=require`` ...).  ``get_async_database_url`` normalises those links so
asyncpg always receives a URL it understands.
"""

from collections.abc import AsyncGenerator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from config import settings


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model."""


def get_async_database_url(url: str | None = None) -> tuple[str, dict]:
    """Return a normalised async URL plus asyncpg ``connect_args``.

    Handles Neon / Railway / Back4App style URLs:

    * ``postgres://`` and ``postgresql://`` become ``postgresql+asyncpg://``.
    * ``sslmode`` is removed from the query string and translated to
      ``connect_args={"ssl": "require"}``.
    * ``channel_binding`` is removed because asyncpg rejects it.
    * ``sqlite://`` becomes ``sqlite+aiosqlite://`` for the test suite.
    """
    raw = (url or settings.database_url).strip()
    if not raw:
        raise ValueError("DATABASE_URL is empty")

    if raw.startswith("postgres://"):
        raw = "postgresql+asyncpg://" + raw[len("postgres://") :]
    elif raw.startswith("postgresql://"):
        raw = "postgresql+asyncpg://" + raw[len("postgresql://") :]
    elif raw.startswith("sqlite://") and not raw.startswith("sqlite+aiosqlite://"):
        raw = "sqlite+aiosqlite://" + raw[len("sqlite://") :]

    is_sqlite = raw.startswith("sqlite")
    connect_args: dict = {}

    if is_sqlite:
        if ":memory:" in raw:
            connect_args["check_same_thread"] = False
        return raw, connect_args

    parts = urlsplit(raw)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))

    ssl_mode = query.pop("sslmode", None)
    ssl_flag = query.pop("ssl", None)
    query.pop("channel_binding", None)
    # asyncpg has no notion of these libpq parameters.
    query.pop("options", None)

    if ssl_mode:
        ssl_mode = ssl_mode.lower()
        if ssl_mode in {"require", "prefer", "allow", "verify-ca", "verify-full"}:
            connect_args["ssl"] = "require"
        elif ssl_mode == "disable":
            connect_args["ssl"] = False
    elif ssl_flag and ssl_flag.lower() in {"1", "true", "yes", "require"}:
        connect_args["ssl"] = "require"

    normalised = urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )
    return normalised, connect_args


DATABASE_URL, CONNECT_ARGS = get_async_database_url()

engine_kwargs: dict = {
    "echo": settings.debug,
    "pool_pre_ping": True,
    "connect_args": CONNECT_ARGS,
}
# SQLite (test suite) must not keep pooled connections across event loops.
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["poolclass"] = NullPool

engine = create_async_engine(DATABASE_URL, **engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an isolated async session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
