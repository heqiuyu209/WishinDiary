from pathlib import Path
import fnmatch
import json
import os
import shlex
import shutil
import subprocess

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


@pytest.fixture
def docker_application_layout(tmp_path):
    """Stage app/scripts from actual COPY rules and honor their context exclusions."""
    layout = tmp_path / 'image'
    patterns = [line.strip() for line in (PROJECT_ROOT / '.dockerignore').read_text().splitlines()
                if line.strip() and not line.startswith('#')]

    def included(source):
        relative = source.relative_to(PROJECT_ROOT).as_posix()
        allowed = True
        for pattern in patterns:
            negate = pattern.startswith('!')
            if fnmatch.fnmatchcase(relative, pattern.lstrip('!')):
                allowed = negate
        return allowed

    for line in (PROJECT_ROOT / 'Dockerfile').read_text().splitlines():
        if not line.startswith('COPY '):
            continue
        parts = shlex.split(line)
        if not parts or parts[0] != 'COPY' or parts[1].split('/')[0] not in ('app', 'scripts'):
            continue
        assert len(parts) == 3
        source, destination = PROJECT_ROOT / parts[1], layout / parts[2]
        if source.is_dir():
            for file in source.rglob('*'):
                if file.is_file() and '__pycache__' not in file.parts and included(file):
                    target = destination / file.relative_to(source)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(file, target)
        elif included(source):
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
    return layout


@pytest.fixture
def assert_private_file():
    def check(path):
        if os.name != 'nt':
            assert path.stat().st_mode & 0o777 == 0o600
            return
        # POSIX mode bits cannot describe Windows DACLs. Inspect the actual
        # access rules and require an explicit grant only to the current user.
        script = """
$ErrorActionPreference = 'Stop'
$acl = [System.IO.File]::GetAccessControl($env:WISHIN_PRIVATE_FILE)
$sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$rules = @($acl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier]))
@{ protected = $acl.AreAccessRulesProtected; owner = $sid; rules = @($rules | ForEach-Object {
  @{ sid = $_.IdentityReference.Value; type = [string]$_.AccessControlType;
     inherited = $_.IsInherited; rights = [int]$_.FileSystemRights }
}) } | ConvertTo-Json -Compress -Depth 4
"""
        powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        result = subprocess.run(
            [str(powershell), '-NoProfile', '-NonInteractive', '-Command', script],
            check=True, capture_output=True, env={**os.environ, 'WISHIN_PRIVATE_FILE': str(path)},
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        acl = json.loads(result.stdout)
        assert acl['protected']
        assert len(acl['rules']) == 1
        rule = acl['rules'][0]
        assert rule['sid'] == acl['owner'] and rule['type'] == 'Allow'
        assert not rule['inherited']
        assert rule['rights'] == 2032127  # FileSystemRights.FullControl
    return check


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
        cursor.execute("TRUNCATE TABLE reminder_deliveries;")
        cursor.execute("TRUNCATE TABLE email_verifications;")
        cursor.execute("TRUNCATE TABLE prediction_logs;")
        cursor.execute("TRUNCATE TABLE daily_log_revisions;")
        cursor.execute("TRUNCATE TABLE daily_logs;")
        cursor.execute("TRUNCATE TABLE cycle_revisions;")
        cursor.execute("TRUNCATE TABLE research_consent_events;")
        cursor.execute("TRUNCATE TABLE research_background_revisions;")
        cursor.execute("TRUNCATE TABLE cycle_tracking_events;")
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
