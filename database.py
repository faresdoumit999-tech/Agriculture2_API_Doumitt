from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
# 🌟 التعديل السحري: استبدلنا os و dotenv بـ "وزير الخارجية" تبعنا
from config import settings

# نجلب الرابط المركزي الآمن المفحوص بواسطة Pydantic Settings
SQLALCHEMY_DATABASE_URL = settings.database_url

# 🌟 الخدعة الهندسية تبعك بنخليها متل ما هي!
# مشان تضل تحميك لو الدوكر بعت الرابط القديم، بس هالمرة عم نطبقها على متغير الـ settings
if SQLALCHEMY_DATABASE_URL and SQLALCHEMY_DATABASE_URL.startswith("postgresql://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

# 1. إنشاء المحرك غير المتزامن (الصاروخ)
engine = create_async_engine(SQLALCHEMY_DATABASE_URL, echo=True)

# 2. إنشاء الجلسة غير المتزامنة (AsyncSession)
SessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()

# 3. دالة جلب قاعدة البيانات (صارت async واحترافية)
async def get_db():
    async with SessionLocal() as session:
        yield session