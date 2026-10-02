from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from config import settings

SQLALCHEMY_DATABASE_URL = settings.database_url

if SQLALCHEMY_DATABASE_URL and SQLALCHEMY_DATABASE_URL.startswith("postgresql://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

# تفعيل التشفير القياسي إذا كنا نتصل بسيرفرات Neon (بدون إخفاء الـ SNI)
connect_args = {}
if SQLALCHEMY_DATABASE_URL and "neon.tech" in SQLALCHEMY_DATABASE_URL:
    # استخدام "require" يخبر asyncpg بتفعيل التشفير بأمان بدون تعقيدات شهادات الويندوز
    connect_args = {"ssl": "require"}

engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    echo=True,
    connect_args=connect_args
)

SessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()

async def get_db():
    async with SessionLocal() as session:
        yield session