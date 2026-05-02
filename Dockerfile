# 1. جيب كمبيوتر وهمي صغير منزل عليه بايثون 3.13 (نفس نسختك)
FROM python:3.13-slim

# 2. حدد مجلد العمل جوا الحاوية (مثل ما بتعمل cd بالتيرمينال)
WORKDIR /app

# 3. انسخ ملف المتطلبات أولاً (تطبيقاً لمبدأ الـ Layer Caching)
COPY requirements.txt .

# 4. نزل المكتبات (بدون كاش لحتى نوفر مساحة)
RUN pip install --no-cache-dir -r requirements.txt

# 5. هلق انسخ باقي ملفات المشروع (main.py, templates, etc)
COPY . .

# 6. افتح الباب رقم 8000 ليتواصل مع العالم الخارجي (Port Mapping)
EXPOSE 8000

# 7. الأمر اللي رح يشتغل أول ما نشغل الحاوية (تشغيل السيرفر)
#CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]