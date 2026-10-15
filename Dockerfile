# ==========================================
# المرحلة الأولى: البناء (Builder Stage)
# ==========================================
FROM python:3.13-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt

# ==========================================
# المرحلة الثانية: التشغيل النهائي (Runner Stage)
# ==========================================
FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY --from=builder /app/wheels /wheels
COPY --from=builder /app/requirements.txt .
RUN pip install --no-cache /wheels/*

COPY . .

EXPOSE 8000

# 1) ينفّذ الـ migrations، وإذا فشلت بيطبع السبب ويكمل (السيرفر ما بيموت)
# 2) يشغّل uvicorn على البورت اللي بتعطيه المنصة ($PORT) أو 8000 افتراضياً
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]