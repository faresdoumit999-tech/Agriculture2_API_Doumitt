import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
import sys
import os

# 1. إخبار بايثون بمكان المشروع الأساسي ليتعرف على ملفاتك
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# 2. استيراد الإعدادات والجداول الخاصة بك
from config import settings
from database import Base
import models # ضروري جداً لكي يقرأ كل الجداول

# إعدادات Alembic الأساسية
config = context.config

# 3. سحب رابط قاعدة البيانات بأمان من ملف .env (بدون هارد كود)
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 4. ربط الـ Metadata ليقوم Alembic بمقارنة الكود بقاعدة البيانات
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """تشغيل الهجرات بوضع الأوفلاين (لتوليد أوامر SQL فقط)"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations() -> None:
    """الاتصال غير المتزامن (Async) بقاعدة البيانات لتطبيق التعديلات"""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()

def run_migrations_online() -> None:
    """تشغيل الهجرات بوضع الأونلاين"""
    asyncio.run(run_async_migrations())

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()