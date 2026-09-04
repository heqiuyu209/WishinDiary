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
    # 长期刷新令牌有效期（天）：access token 过期后用于无感续期；
    # 退出登录或刷新轮换时服务端撤销（见 refresh_tokens 表）。
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    MODEL_PATH: Path = PROJECT_ROOT / "ml" / "menstrual_rf_model.skops"
    MODEL_SHA256: str = ""

    # 数据保留策略：
    # DATA_RETENTION_DAYS 定义健康数据（周期/日志/预测记录）在数据库中的最长保留天数。
    # 0 表示无限期保留（默认）；>0 时可由 scripts/cleanup_expired_data.py 定期清理。
    DATA_RETENTION_DAYS: int = 0
    # 数据导出中是否包含 AI 日志与个性化建议（true 时导出全部，false 仅导出用户核心数据）
    EXPORT_INCLUDE_AI_LOGS: bool = True

    # ---- 可观测性配置 ----
    # 模型监控 JSONL（ml/monitoring_logs/）保留天数：
    # 超过保留期的预测事件分片文件在写入时自动清理（0 = 永久保留）。
    MONITOR_RETENTION_DAYS: int = 90
    # 日志输出格式：json（生产推荐，结构化单行 JSON）| text（开发可读）
    LOG_FORMAT: str = "json"
    # 日志级别：DEBUG | INFO | WARNING | ERROR | CRITICAL
    LOG_LEVEL: str = "INFO"
    # 是否启用 /metrics Prometheus 文本端点（false 时仅输出结构化日志指标）
    METRICS_ENABLED: bool = False
    # Sentry DSN，留空则完全不初始化 Sentry（env 可开关）
    SENTRY_DSN: str = ""
    # Sentry 性能追踪采样率（0~1），仅在 SENTRY_DSN 非空时生效
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1

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


def validate_observability_config() -> None:
    """校验可观测性相关配置，错误时快速失败（Fail fast）。

    部署前检查脚本 scripts/check_production.py 也会复用本函数，
    保证启动期与部署前校验口径一致。
    """
    import logging as _logging

    if settings.LOG_FORMAT not in {"json", "text"}:
        raise RuntimeError(
            f"LOG_FORMAT must be 'json' or 'text', got '{settings.LOG_FORMAT}'"
        )
    # 校验日志级别是否为合法 logging 级别名
    level = _logging.getLevelName(settings.LOG_LEVEL.upper())
    if not isinstance(level, int):
        raise RuntimeError(
            f"LOG_LEVEL must be a valid logging level, got '{settings.LOG_LEVEL}'"
        )
    if not 0.0 <= settings.SENTRY_TRACES_SAMPLE_RATE <= 1.0:
        raise RuntimeError("SENTRY_TRACES_SAMPLE_RATE must be within [0, 1]")
    if settings.MONITOR_RETENTION_DAYS < 0:
        raise RuntimeError("MONITOR_RETENTION_DAYS must be >= 0 (0 = keep monitoring logs forever)")


validate_security_baseline()
validate_observability_config()
