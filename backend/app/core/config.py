from pydantic_settings import BaseSettings
from functools import lru_cache
import os

class Settings(BaseSettings):
    # App Info
    APP_NAME: str = "CPQ Platform"
    APP_VERSION: str = "0.1.11"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # PostgreSQL Configuration
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "961216")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "cpq_platform")

    # Database URL (auto-constructed from components)
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}?client_encoding=UTF8"

    # Data path (DBs, Configs, Projects) - kept for backward compatibility
    DATA_PATH: str = os.getenv("DATA_PATH", r"D:\Quotation_Automation")

    # CORS Configuration
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    class Config:
        env_file = ".env"
        extra = "allow"

@lru_cache()
def get_settings() -> Settings:
    return Settings()
