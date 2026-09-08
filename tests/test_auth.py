import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

async def test_register_user(client: AsyncClient):
    """اختبار مسار إنشاء حساب جديد"""
    user_data = {
        "username": "test_farmer",
        "password": "securepassword123"
    }

    response = await client.post("/api/register", json=user_data)

    # 1. التعديل هنا: فحص كود 201 بدلاً من 200
    assert response.status_code == 201
    assert response.json()["message"] == "User created successfully"

async def test_login_user(client: AsyncClient):
    """اختبار تسجيل الدخول بنجاح واستلام التوكن"""
    user_data = {"username": "test_farmer", "password": "securepassword123"}
    register_response = await client.post("/api/register", json=user_data)
    assert register_response.status_code == 201

    login_data = {
        "username": "test_farmer",
        "password": "securepassword123"
    }
    response = await client.post("/api/login", data=login_data)

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

async def test_login_wrong_password(client: AsyncClient):
    """اختبار الحماية: تسجيل الدخول بكلمة مرور خاطئة"""
    user_data = {"username": "test_farmer", "password": "securepassword123"}
    await client.post("/api/register", json=user_data)

    wrong_login_data = {
        "username": "test_farmer",
        "password": "wrongpassword!"
    }
    response = await client.post("/api/login", data=wrong_login_data)

    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect username or password"

async def test_get_summary_with_token(client: AsyncClient):
    """اختبار مسار محمي: جلب الملخص باستخدام التوكن"""
    user_data = {"username": "farmer_vip", "password": "supersecret"}
    await client.post("/api/register", json=user_data)

    login_res = await client.post("/api/login", data=user_data)
    token = login_res.json()["access_token"]

    headers = {"Authorization": f"Bearer {token}"}
    response = await client.get("/api/summary", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total_income"] == 0.0
    assert data["total_expenses"] == 0.0
    assert data["net_profit"] == 0.0

async def test_summary_without_token(client: AsyncClient):
    """اختبار الحماية: محاولة الدخول لمسار محمي بدون توكن"""
    response = await client.get("/api/summary")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"