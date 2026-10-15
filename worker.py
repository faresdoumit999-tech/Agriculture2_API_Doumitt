import time
from celery import Celery
from config import settings

# 1. إنشاء كائن Celery وربطه بـ Redis (صندوق البريد الذي يستلم منه المهام)
celery_app = Celery(
    "doumitt_worker",
    broker=settings.redis_url,
    backend=settings.redis_url
)

# 2. إعدادات لتسريع وتوحيد نوع البيانات المرسلة
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)


# 3. مهمة وهمية (تأخذ 10 ثوانٍ) لنجرب عليها
@celery_app.task(name="generate_heavy_report")
def generate_heavy_report_task(user_id: int):
    print(f"⚙️ [Celery] بدء معالجة التقرير الثقيل للمستخدم {user_id}...")

    # محاكاة لعملية معقدة جداً تأخذ 10 ثوانٍ (مثل حساب 50 ألف فاتورة)
    time.sleep(10)

    print(f"✅ [Celery] تم الانتهاء من تقرير المستخدم {user_id}!")
    return {"status": "success", "user_id": user_id, "message": "Report generated!"}