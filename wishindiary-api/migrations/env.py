"""Alembic 迁移运行环境。

设计要点：
1. 数据库 URL 解析顺序：config.attributes > alembic.ini > settings（环境变量 / .env）。
   测试环境通过 conftest 显式注入测试库 URL，避免误连开发库。
2. 以 raw SQL 迁移为主（本仓库未引入 ORM 模型），target_metadata 保持 None。
3. app 包通过项目根目录加入 sys.path 后导入，保证在任意工作目录下可运行。
"""

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# 将 wishindiary-api 项目根目录加入 sys.path，以便导入 app 包
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.core.config import settings  # noqa: E402
from app.core.database_url import build_database_url  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# URL 对象通过 attributes 传递，不把含 % 的凭据写回 ConfigParser。
configured_url = config.attributes.get("sqlalchemy_url")
if configured_url is None:
    configured_url = config.get_main_option("sqlalchemy.url")
    if not configured_url or configured_url.strip() in ("", "driver://"):
        configured_url = build_database_url(settings)

target_metadata = None


def run_migrations_offline() -> None:
    """以离线模式运行迁移（只生成 SQL，不连接数据库）。"""
    context.configure(
        url=configured_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：连接数据库并执行迁移。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        url=configured_url,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
