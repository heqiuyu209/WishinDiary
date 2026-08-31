"""Environment-backed application settings with safe production defaults."""

from pathlib import Path
import secrets

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"  # development | production | test

    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_USER: str = "wishin_app"
    DB_PASSWORD: str = ""
    DB_NAME: str = "wishindiary_db"

    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 天

    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    MODEL_PATH: Path = PROJECT_ROOT / "ml" / "menstrual_rf_model.skops"
    MODEL_SHA256: str = ""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def cors_origins(self) -> list[str]:
        return [value.strip() for value in self.CORS_ORIGINS.split(",") if value.strip()]

    @property
    def model_abs_path(self) -> Path:
        return self.MODEL_PATH

settings = Settings()


def validate_security_baseline() -> None:
    """Fail closed in production and use an ephemeral key for local development."""
    weak_passwords = {"", "123456", "root", "password"}
    if not settings.SECRET_KEY:
        if settings.ENVIRONMENT == "production":
            raise RuntimeError("SECRET_KEY must be supplied in production")
        settings.SECRET_KEY = secrets.token_urlsafe(32)
    if settings.ENVIRONMENT == "production" and len(settings.SECRET_KEY) < 32:
        raise RuntimeError("SECRET_KEY must be at least 32 characters in production")
    if settings.ENVIRONMENT == "production" and settings.DB_PASSWORD in weak_passwords:
        raise RuntimeError("A strong DB_PASSWORD is required in production")
    if settings.ENVIRONMENT == "production":
        if not settings.MODEL_PATH.exists():
            raise RuntimeError(f"Production model is missing: {settings.MODEL_PATH}")
        if not settings.MODEL_SHA256:
            raise RuntimeError("MODEL_SHA256 is required in production")
    if settings.ALGORITHM != "HS256":
        raise RuntimeError("Only the audited HS256 JWT algorithm is supported")


validate_security_baseline()
