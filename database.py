from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from config import settings


def get_async_database_url():
    url = make_url(settings.database_url)
    if url.drivername in ("postgresql", "postgres", "postgresql+psycopg2"):
        url = url.set(drivername="postgresql+asyncpg")
    query = {k: v for k, v in url.query.items()
             if k not in ("sslmode", "ssl", "channel_binding")}
    return url.set(query=query)


def get_connect_args():
    host = make_url(settings.database_url).host or ""
    return {"ssl": "require"} if "neon.tech" in host else {}


engine = create_async_engine(
    get_async_database_url(),
    echo=False,
    pool_pre_ping=True,
    connect_args=get_connect_args(),
)

SessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


async def get_db():
    async with SessionLocal() as session:
        yield session