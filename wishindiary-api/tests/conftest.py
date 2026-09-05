from pathlib import Path

import pytest
import pymysql
from fastapi.testclient import TestClient
from alembic import command
from alembic.config import Config

from app.main import app
from app.core.config import settings
from app.core.database_url import build_database_url
from app.core import database

TEST_DB_NAME = "wishindiary_test_db"

# wishindiary-api 项目根目录（alembic.ini 所在目录）
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"


def _alembic_upgrade_to_head(test_db_name: str) -> None:
    """在指定数据库上运行 Alembic 迁移到 head，统一由迁移文件建表。

    数据库结构只维护在 migrations/versions/ 中（收敛自 schema.sql 与旧 conftest），
    Alembic 会记录版本号，保证本地 Docker 与 pytest 测试建表一致。
    """
    cfg = Config(str(ALEMBIC_INI))
    cfg.attributes["sqlalchemy_url"] = build_database_url(settings, test_db_name)
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """测试会话开始前，自动创建测试库并通过 Alembic 迁移建表。

    关键：把 app.core.database 的连接池切换到测试库，
    避免测试误写生产库 (wishindiary_db)。
    """
    conn = pymysql.connect(
        host=settings.DB_HOST,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        autocommit=True
    )
    with conn.cursor() as cursor:
        # 重建测试库，保证 Alembic 从空库开始建表（兼容旧 conftest 内联建表的残留表）
        cursor.execute(f"DROP DATABASE IF EXISTS {TEST_DB_NAME};")
        cursor.execute(f"CREATE DATABASE {TEST_DB_NAME} DEFAULT CHARACTER SET utf8mb4;")
    conn.close()

    # 通过 Alembic 迁移建表（含版本表 alembic_version）
    _alembic_upgrade_to_head(TEST_DB_NAME)

    # 让应用连接池指向测试库，隔离生产数据
    database.pool.close()
    database.pool = database.PooledDB(
        creator=pymysql,
        maxconnections=20,
        mincached=0,
        maxcached=5,
        blocking=True,
        host=settings.DB_HOST,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=TEST_DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    yield
    # 测试结束后还原
    database.pool.close()
    database.pool = database.PooledDB(
        creator=pymysql,
        maxconnections=20,
        mincached=5,
        maxcached=10,
        blocking=True,
        host=settings.DB_HOST,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


@pytest.fixture(autouse=True)
def truncate_tables():
    """每个 test 函数运行后自动清空数据，实现测试用例数据隔离"""
    yield
    db_conn = pymysql.connect(
        host=settings.DB_HOST,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=TEST_DB_NAME,
        autocommit=True
    )
    with db_conn.cursor() as cursor:
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
        # 登录限流表必须一并清空，防止跨用例累计触发 429
        cursor.execute("TRUNCATE TABLE login_attempts;")
        cursor.execute("TRUNCATE TABLE refresh_tokens;")
        cursor.execute("TRUNCATE TABLE prediction_logs;")
        cursor.execute("TRUNCATE TABLE daily_logs;")
        cursor.execute("TRUNCATE TABLE cycles;")
        cursor.execute("TRUNCATE TABLE users;")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
    db_conn.close()


@pytest.fixture
def client():
    """ FastApi 测试客户端 """
    return TestClient(app)


@pytest.fixture
def auth_header(client):
    """注册并登录测试用户，返回空 headers（认证凭据在 HttpOnly Cookie 中）。

    登录接口已不再在响应体返回 access_token；TestClient 会保留
    Set-Cookie 并自动随后续请求携带，因此业务接口仅需依赖 Cookie。
    """
    user_payload = {"username": "test_user", "password": "password123"}
    client.post("/api/v1/auth/register", json=user_payload)
    response = client.post("/api/v1/auth/login", json=user_payload)
    assert response.status_code == 200, response.text
    assert "access_token" not in response.json(), "登录响应体不应再携带 JWT"
    return {}
