import pytest
from httpx import AsyncClient

# إخبار Pytest أن كل الاختبارات هنا غير متزامنة
pytestmark = pytest.mark.asyncio

# فاتورة وهمية للاختبار
SAMPLE_INVOICE = {
    "date": "2026-09-07",
    "total_gross": 1000.0,
    "deductions": 50.0,
    "net_total": 950.0,
    "items": [
        {
            "crop_name": "طماطم",
            "box_count": 100,
            "net_weight": 500.0,
            "unit_price": 2.0,
            "subtotal": 1000.0
        }
    ]
}


async def test_add_invoice(client: AsyncClient, logged_in_token: str):
    """اختبار إضافة فاتورة جديدة للمزارع"""
    # 1. تجهيز الترويسة باستخدام التوكن السحري الذي جلبته الأداة
    headers = {"Authorization": f"Bearer {logged_in_token}"}

    # 2. إرسال طلب الإضافة
    response = await client.post("/api/invoices", json=SAMPLE_INVOICE, headers=headers)

    # 3. التحقق من نجاح العملية والحسابات
    assert response.status_code == 201
    data = response.json()
    assert data["net_total"] == 950.0
    assert len(data["items"]) == 1
    assert data["items"][0]["crop_name"] == "طماطم"


async def test_get_invoices(client: AsyncClient, logged_in_token: str):
    """اختبار جلب قائمة فواتير المزارع"""
    headers = {"Authorization": f"Bearer {logged_in_token}"}

    # نضيف فاتورة أولاً لضمان وجود بيانات
    await client.post("/api/invoices", json=SAMPLE_INVOICE, headers=headers)

    # نجلب الفواتير
    response = await client.get("/api/invoices", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["total_gross"] == 1000.0


async def test_update_invoice(client: AsyncClient, logged_in_token: str):
    """اختبار تعديل الخصومات في فاتورة وإعادة حساب الصافي"""
    headers = {"Authorization": f"Bearer {logged_in_token}"}

    # 1. إنشاء الفاتورة
    create_res = await client.post("/api/invoices", json=SAMPLE_INVOICE, headers=headers)
    invoice_id = create_res.json()["id"]

    # 2. تعديل الخصم ليصبح 100 بدلاً من 50 (عبر الـ Query Parameter كما برمجتها)
    response = await client.patch(f"/api/invoices/{invoice_id}?new_deductions=100.0", headers=headers)

    # 3. التحقق من أن السيرفر قام بإعادة حساب الصافي بشكل صحيح
    assert response.status_code == 200
    data = response.json()
    assert data["deductions"] == 100.0
    assert data["net_total"] == 900.0  # 1000 - 100


async def test_delete_invoice(client: AsyncClient, logged_in_token: str):
    """اختبار حذف فاتورة بالكامل"""
    headers = {"Authorization": f"Bearer {logged_in_token}"}

    # 1. إنشاء الفاتورة
    create_res = await client.post("/api/invoices", json=SAMPLE_INVOICE, headers=headers)
    invoice_id = create_res.json()["id"]

    # 2. حذف الفاتورة
    delete_res = await client.delete(f"/api/invoices/{invoice_id}", headers=headers)

    assert delete_res.status_code == 200
    assert "تم حذف الفاتورة" in delete_res.json()["message"]

    # 3. التأكد من أنها حذفت فعلاً بمحاولة جلبها مجدداً (نبحث في مسار الملخص كمثال للتأكد من اختفاء أرقامها)
    summary_res = await client.get("/api/summary", headers=headers)
    assert summary_res.json()["total_income"] == 0.0