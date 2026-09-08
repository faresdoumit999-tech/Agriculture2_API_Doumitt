from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str
    secret_key: str
    redis_url: str

    # الطريقة الحديثة (Pydantic V2) لقراءة ملف البيئة
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

# هي النسخة اللي رح نستخدمها بكل المشروع
settings = Settings()