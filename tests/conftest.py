import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# استيراد ملفات مشروعك
from main import app, get_db
from models import Base

# 1. إنشاء رابط لقاعدة بيانات وهمية (SQLite سريعة للـ Testing)
SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///./test_doumitt.db"

# إعداد المحرك الوهمي
engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}  # ضرورية لـ SQLite
)

TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine, class_=AsyncSession
)


# 2. Fixture لتجهيز الجداول قبل كل اختبار ومسحها بعده
@pytest_asyncio.fixture(scope="function")
async def db_session():
    # إنشاء الجداول الوهمية
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # فتح جلسة اتصال
    async with TestingSessionLocal() as session:
        yield session  # تسليم الجلسة لدالة الاختبار

    # مسح الجداول بعد انتهاء الاختبار لتنظيف البيئة
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# 3. Fixture المتصفح الوهمي (TestClient) + تبديل الداتا بيز
@pytest_asyncio.fixture(scope="function")
async def client(db_session):
    # دالة لخداع السيرفر ليستخدم الداتا بيز الوهمية
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    # تشغيل المتصفح الوهمي السريع
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    # إرجاع السيرفر لحالته الطبيعية بعد الاختبار
    app.dependency_overrides.clear()