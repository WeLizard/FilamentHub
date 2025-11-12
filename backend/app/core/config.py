"""Application configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    # Project
    PROJECT_NAME: str = "FilamentHub"
    VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False
    BASE_URL: str = "https://filamenthub.ru"  # Базовый URL для QR-кодов

    # Database
    DATABASE_URL: str
    DATABASE_ECHO: bool = False
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_POOL_TIMEOUT: int = 30  # seconds
    DATABASE_POOL_RECYCLE: int = 1800  # seconds (30 minutes)

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 дней (10080 минут)
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30  # 30 дней для refresh token

    # CORS
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8080",
    ]

    # Pagination
    DEFAULT_PAGE_SIZE: int = 50
    MAX_PAGE_SIZE: int = 100

    # File Upload
    MAX_UPLOAD_SIZE_MB: int = 50
    MAX_FILES_PER_REQUEST: int = 10  # Максимум файлов на одну заявку
    UPLOAD_DIR: str = "uploads"
    ALLOWED_PROOF_FILE_EXTENSIONS: list[str] = [".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx"]
    # Автоматическая очистка файлов от завершенных/отклоненных заявок через N дней
    CLEANUP_FILES_AFTER_DAYS: int = 30

    # OrcaSlicer bundles
    ORCA_SYSTEM_PRESETS_PATH: str = "docs/orca_bundles/system_presets"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


# Global settings instance
settings = Settings()

