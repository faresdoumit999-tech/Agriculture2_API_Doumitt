# ==========================================
# المرحلة الأولى: البناء (Builder Stage)
# ==========================================
FROM python:3.13-slim as builder

WORKDIR /app

# منع بايثون من كتابة ملفات مؤقتة وتخزين الكاش
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# تثبيت أدوات النظام الأساسية المطلوبة لترجمة بعض المكتبات (مثل asyncpg)
RUN apt-get update && apt-get install -y gcc

# نسخ ملف المتطلبات وتحويل المكتبات إلى صيغة "عجلات" (Wheels) لتسريع التثبيت لاحقاً
COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt

# ==========================================
# المرحلة الثانية: التشغيل النهائي (Runner Stage)
# ==========================================
FROM python:3.13-slim

WORKDIR /app

# استيراد المكتبات الجاهزة من المرحلة الأولى فقط (بدون أدوات البناء مثل gcc)
COPY --from=builder /app/wheels /wheels
COPY --from=builder /app/requirements.txt .

# تثبيت المكتبات الجاهزة بدون الحاجة للاتصال بالإنترنت أو الترجمة
RUN pip install --no-cache /wheels/*

# نسخ كود المشروع النظيف
COPY . .

# كشف المنفذ للسيرفر
EXPOSE 8000

# أمر التشغيل الاحترافي للسيرفر
# تشغيل هجرات Alembic تلقائياً لبناء/تحديث الجداول ثم إقلاع السيرفر
CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000"]