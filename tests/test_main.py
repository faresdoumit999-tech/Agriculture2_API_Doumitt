from fastapi.testclient import TestClient
from main import app

# إنشاء متصفح وهمي لاختبار التطبيق
client = TestClient(app)


def test_register_endpoint():
    # محاكاة إرسال بيانات مزارع جديد
    response = client.post(
        "/api/register",
        json={"username": "test_farmer_999", "password": "strongpassword123"}
    )

    # نحن نتوقع إما 200 (تم الإنشاء) أو 400 (المستخدم موجود مسبقاً)
    # المهم أن لا ينهار السيرفر ويعطينا 500!
    assert response.status_code in [200, 400]