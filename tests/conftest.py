"""Pytest fixtures: isolated SQLite database and async API client."""

from __future__ import annotations

import os

os.environ["SECRET_KEY"] = "test-secret-key-with-more-than-sixteen-chars"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_doumitt.db"
os.environ["CACHE_ENABLED"] = "false"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["ENVIRONMENT"] = "test"
os.environ["DEBUG"] = "false"

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from database import Base, engine  # noqa: E402
from main import app  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def prepare_database():
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client


async def register_and_login(
    client: AsyncClient,
    username: str = "farmer1",
    password: str = "secret123",
) -> dict[str, str]:
    register = await client.post(
        "/api/register",
        json={"username": username, "password": password, "phone_number": "0999999999"},
    )
    assert register.status_code == 201, register.text

    login = await client.post(
        "/api/login",
        data={"username": username, "password": password},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def create_project(client: AsyncClient, headers: dict[str, str]) -> dict:
    response = await client.post(
        "/api/projects",
        headers=headers,
        json={
            "name": "مشروع الأرض القبلية - قسم أ",
            "greenhouse_count": 10,
            "crops_planted": "باذنجان، خيار",
            "season_start_date": "2026-01-01",
            "season_end_date": None,
            "is_active": True,
            "has_sharecropper": True,
            "sharecropper_name": "أبو أحمد",
            "sharecropper_profit_pct": 20,
            "sharecropper_expense_pct": 20,
            "notes": "موسم تجريبي",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()
