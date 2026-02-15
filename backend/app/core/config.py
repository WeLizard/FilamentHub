"""Application configuration."""

from urllib.parse import quote_plus
from pydantic import model_validator
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
    # Если DATABASE_URL задан напрямую - используем его, иначе формируем из отдельных переменных
    DATABASE_URL: str | None = None
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "filamenthub"
    POSTGRES_PASSWORD: str = "filamenthub"
    POSTGRES_DB: str = "filamenthub"
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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60  # 1 час (короткоживущий для безопасности)
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30  # 30 дней для refresh token (долгоживущий для удобства)

    # CORS
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8080",
        "https://filamenthub.ru",
        "https://www.filamenthub.ru",
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
    
    # Distributions (downloadable files)
    DISTRIBUTIONS_DIR: str = "distributions"
    ORCASLICER_DISTRIBUTIONS_DIR: str = "distributions/orcaslicer"
    
    # QR codes
    QR_CODES_DIR: str = "uploads/qr_codes"  # Изображения QR-кодов для печати

    # reCAPTCHA v3
    RECAPTCHA_SECRET_KEY: str = ""  # Пустая строка = пропуск проверки (для разработки)
    RECAPTCHA_SCORE_THRESHOLD: float = 0.5

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    @model_validator(mode='after')
    def build_database_url(self) -> 'Settings':
        """Формируем DATABASE_URL из отдельных переменных с правильным экранированием пароля."""
        # ВСЕГДА формируем DATABASE_URL из отдельных переменных
        # с правильным URL-encoding пароля (для поддержки паролей с @, #, и т.д.)
        encoded_password = quote_plus(self.POSTGRES_PASSWORD)
        self.DATABASE_URL = (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{encoded_password}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )
        return self


# Global settings instance
settings = Settings()

