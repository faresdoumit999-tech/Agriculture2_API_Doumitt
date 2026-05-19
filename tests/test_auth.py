import pytest
from httpx import AsyncClient

# هذه العلامة تخبر pytest أن جميع الاختبارات في هذا الملف غير متزامنة (async)
pytestmark = pytest.mark.asyncio


async def test_register_user(client: AsyncClient):
    """اختبار مسار إنشاء حساب جديد"""
    # 1. تجهيز البيانات
    user_data = {
        "username": "test_farmer",
        "password": "securepassword123"
    }

    # 2. إرسال الطلب (محاكاة ضغطة زر التسجيل)
    response = await client.post("/api/register", json=user_data)

    # 3. التأكد من النتيجة (Assertions)
    assert response.status_code == 200
    assert response.json()["message"] == "User created successfully"


async def test_login_user(client: AsyncClient):
    """اختبار تسجيل الدخول بنجاح واستلام التوكن"""
    # 1. إنشاء مستخدم أولاً (لأن الداتا بيز بتنظف حالها بعد كل اختبار)
    user_data = {"username": "test_farmer", "password": "securepassword123"}
    await client.post("/api/register", json=user_data)

    # 2. محاكاة تسجيل الدخول (نرسل البيانات كـ Form Data)
    login_data = {
        "username": "test_farmer",
        "password": "securepassword123"
    }
    response = await client.post("/api/login", data=login_data)

    # 3. التأكد من نجاح الدخول واستلام التوكن
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


async def test_login_wrong_password(client: AsyncClient):
    """اختبار الحماية: تسجيل الدخول بكلمة مرور خاطئة"""
    # 1. إنشاء المستخدم الأصلي
    user_data = {"username": "test_farmer", "password": "securepassword123"}
    await client.post("/api/register", json=user_data)

    # 2. محاولة الدخول بباسوورد غلط
    wrong_login_data = {
        "username": "test_farmer",
        "password": "wrongpassword!"
    }
    response = await client.post("/api/login", data=wrong_login_data)

    # 3. التأكد من أن النظام قام بصده ورده بخطأ 401
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect username or password"


async def test_get_summary_with_token(client: AsyncClient):
    """اختبار مسار محمي: جلب الملخص باستخدام التوكن"""
    # 1. إنشاء حساب وتسجيل الدخول لأخذ الـ Token
    user_data = {"username": "farmer_vip", "password": "supersecret"}
    await client.post("/api/register", json=user_data)

    login_res = await client.post("/api/login", data=user_data)
    token = login_res.json()["access_token"]

    # 2. تجهيز الـ Headers (وضع الهوية في الطلب)
    headers = {"Authorization": f"Bearer {token}"}

    # 3. طلب المسار المحمي مع التوكن
    response = await client.get("/api/summary", headers=headers)

    # 4. التحقق من النتيجة (يجب أن تكون الأرقام 0 لأن الحساب جديد)
    assert response.status_code == 200
    data = response.json()
    assert data["total_income"] == 0.0
    assert data["total_expenses"] == 0.0
    assert data["net_profit"] == 0.0


async def test_summary_without_token(client: AsyncClient):
    """اختبار الحماية: محاولة الدخول لمسار محمي بدون توكن"""
    # نضرب على المسار مباشرة بدون تمرير Headers
    response = await client.get("/api/summary")

    # يجب أن يطرده السيرفر بخطأ 401
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"