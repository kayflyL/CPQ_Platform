from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache
import os

_BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/

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

    # LLM (OpenAI-compatible — 官方直连或中转站都行,改 base_url/key/model 即可)
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "") or os.getenv("DASHSCOPE_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "qwen-plus")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

    # CORS Configuration
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    class Config:
        env_file = _BASE_DIR / ".env"
        extra = "allow"

@lru_cache()
def get_settings() -> Settings:
    return Settings()
