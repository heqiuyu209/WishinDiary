"""数据库迁移测试（Alembic upgrade / downgrade）。

覆盖目标：
- upgrade head 后建出全部业务表 + 版本记录；
- downgrade base 能完整回滚（删除全部表）；
- upgrade -> downgrade -> upgrade 往返不报错，保证真实环境可回滚重放。
"""

from pathlib import Path

import pymysql
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.core.config import settings

MIGRATION_TEST_DB = "wishindiary_migration_test_db"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"

EXPECTED_TABLES = {
    "users",
    "cycles",
    "daily_logs",
    "prediction_logs",
    "login_attempts",
    "alembic_version",
}


def _alembic_cfg(db_name: str) -> Config:
    url = (
        f"mysql+pymysql://{settings.DB_USER}:{settings.DB_PASSWORD}"
        f"@{settings.DB_HOST}:{settings.DB_PORT}/{db_name}?charset=utf8mb4"
    )
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _head_revision() -> str:
    """读取迁移脚本目录的 head revision，避免硬编码版本号。"""
    cfg = Config(str(ALEMBIC_INI))
    scripts = ScriptDirectory.from_config(cfg)
    head = scripts.get_current_head()
    assert head, "迁移目录为空，不存在 head revision"
    return head


def _table_names(db_name: str) -> set[str]:
    conn = pymysql.connect(
        host=settings.DB_HOST,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=db_name,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = %s",
                (db_name,),
            )
            return {row[0] for row in cursor.fetchall()}
    finally:
        conn.close()


def _version_num(db_name: str) -> str:
    conn = pymysql.connect(
        host=settings.DB_HOST,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=db_name,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT version_num FROM alembic_version")
            rows = cursor.fetchall()
            assert len(rows) == 1, f"alembic_version 应有且仅有一条记录，实际 {len(rows)}"
            return rows[0][0]
    finally:
        conn.close()


@pytest.fixture(scope="module")
def migration_db():
    """创建独立迁移测试库，并在模块结束后删除。"""
    conn = pymysql.connect(
        host=settings.DB_HOST,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        autocommit=True,
    )
    with conn.cursor() as cursor:
        cursor.execute(f"DROP DATABASE IF EXISTS {MIGRATION_TEST_DB};")
        cursor.execute(
            f"CREATE DATABASE {MIGRATION_TEST_DB} DEFAULT CHARACTER SET utf8mb4;"
        )
    conn.close()
    yield MIGRATION_TEST_DB
    conn = pymysql.connect(
        host=settings.DB_HOST,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        autocommit=True,
    )
    with conn.cursor() as cursor:
        cursor.execute(f"DROP DATABASE IF EXISTS {MIGRATION_TEST_DB};")
    conn.close()


def test_upgrade_head_creates_all_tables(migration_db):
    command.upgrade(_alembic_cfg(migration_db), "head")

    tables = _table_names(migration_db)
    missing = EXPECTED_TABLES - tables
    assert not missing, f"迁移 head 后缺失表: {sorted(missing)}"

    # 版本记录应指向迁移目录的最新 head
    assert _version_num(migration_db) == _head_revision()


def test_downgrade_base_drops_all_tables(migration_db):
    cfg = _alembic_cfg(migration_db)
    command.upgrade(cfg, "head")
    assert EXPECTED_TABLES <= _table_names(migration_db)

    command.downgrade(cfg, "base")

    tables = _table_names(migration_db)
    business_tables = EXPECTED_TABLES - {"alembic_version"}
    remaining = business_tables & tables
    assert not remaining, f"downgrade base 后仍有残留业务表: {sorted(remaining)}"


def test_upgrade_downgrade_upgrade_roundtrip(migration_db):
    """完整往返：upgrade -> downgrade -> upgrade，不得因残留状态报错。"""
    cfg = _alembic_cfg(migration_db)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    tables = _table_names(migration_db)
    assert EXPECTED_TABLES <= tables
    assert _version_num(migration_db) == _head_revision()
