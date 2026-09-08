import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend

from main import app, get_db
from models import Base

# 1. إنشاء رابط لقاعدة بيانات وهمية (تعمل بالـ RAM حصراً)
SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}
)

TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine, class_=AsyncSession
)

@pytest_asyncio.fixture(scope="function")
async def db_session():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestingSessionLocal() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest_asyncio.fixture(scope="function")
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    # تجاوز Redis الفعلي واستخدام كاش وهمي
    FastAPICache.init(InMemoryBackend(), prefix="test-cache")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()

# 3. الأداة الجديدة: إنشاء مستخدم وتسجيل دخوله تلقائياً لإرجاع التوكن
@pytest_asyncio.fixture(scope="function")
async def logged_in_token(client):
    user_data = {"username": "tester_pro", "password": "strongpassword123"}
    await client.post("/api/register", json=user_data)
    response = await client.post("/api/login", data=user_data)
    return response.json()["access_token"]