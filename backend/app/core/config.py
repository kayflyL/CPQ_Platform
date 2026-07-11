from pydantic_settings import BaseSettings
from functools import lru_cache
import os

class Settings(BaseSettings):
    # App Info
    APP_NAME: str = "CPQ Platform"
    APP_VERSION: str = "0.1.11"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Database Configuration
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./data/cpq_platform.db")

    # Data path (DBs, Configs, Projects)
    DATA_PATH: str = os.getenv("DATA_PATH", r"D:\Quotation_Automation")

    # CORS Configuration
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    class Config:
        env_file = ".env"
        extra = "allow"

@lru_cache()
def get_settings() -> Settings:
    return Settings()
