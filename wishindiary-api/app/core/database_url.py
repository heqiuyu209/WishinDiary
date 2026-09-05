"""SQLAlchemy 连接地址：直接传递原始凭据，避免 URL 与 INI 双重转义。"""

from sqlalchemy import URL

from app.core.config import Settings


def build_database_url(settings: Settings, database: str | None = None) -> URL:
    return URL.create(
        "mysql+pymysql",
        username=settings.DB_USER,
        password=settings.DB_PASSWORD,
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        database=database if database is not None else settings.DB_NAME,
        query={"charset": "utf8mb4"},
    )
