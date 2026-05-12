from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
import os
from dotenv import load_dotenv

load_dotenv()

# نجلب الرابط من ملف .env
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

# 🌟 الخدعة الهندسية: إجبار النظام على استخدام asyncpg حتى لو الدوكر معلق على الرابط القديم
if SQLALCHEMY_DATABASE_URL and SQLALCHEMY_DATABASE_URL.startswith("postgresql://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

# 1. إنشاء المحرك غير المتزامن (الصاروخ) بدال القديم
engine = create_async_engine(SQLALCHEMY_DATABASE_URL, echo=True)

# 2. إنشاء الجلسة غير المتزامنة (AsyncSession)
SessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()

# 3. دالة جلب قاعدة البيانات (صارت async)
async def get_db():
    async with SessionLocal() as session:
        yield session