"""部署回归：迁移凭据不被误解析，HTTP/HTTPS 会话行为符合显式配置。"""

import runpy
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock

import pytest
import sqlalchemy
from alembic import context
from alembic.config import Config
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


@pytest.mark.parametrize("offline", [True, False])
@pytest.mark.parametrize("source", ["settings", "attribute", "ini"])
def test_migration_preserves_special_credentials(monkeypatch, offline, source):
    password = "test@2026!Secure%40:/?# +"
    url = sqlalchemy.URL.create(
        "mysql+pymysql", username="test@user", password=password,
        host="db", port=3306, database="migration_probe", query={"charset": "utf8mb4"},
    )
    cfg = Config()
    if source == "attribute":
        cfg.attributes["sqlalchemy_url"] = url
    elif source == "ini":
        cfg.set_main_option("sqlalchemy.url", url.render_as_string(hide_password=False).replace("%", "%%"))
    else:
        for name, value in {
            "DB_USER": url.username, "DB_PASSWORD": password, "DB_HOST": "db",
            "DB_PORT": 3306, "DB_NAME": "migration_probe",
        }.items():
            monkeypatch.setattr(settings, name, value)

    captured = {}

    def capture_engine(options, **kwargs):
        # 创建引擎但不连接：验证实际 PyMySQL 参数，而不使用测试凭据访问数据库。
        engine = sqlalchemy.create_engine(kwargs["url"])
        captured["params"] = engine.dialect.create_connect_args(engine.url)[1]
        engine.dispose()
        return Mock(connect=lambda: nullcontext(Mock()))

    def capture_configure(**kwargs):
        if "url" in kwargs:
            capture_engine({}, url=kwargs["url"])

    monkeypatch.setattr(context, "config", cfg, raising=False)
    monkeypatch.setattr(context, "is_offline_mode", lambda: offline)
    monkeypatch.setattr(context, "configure", capture_configure)
    monkeypatch.setattr(context, "begin_transaction", nullcontext)
    monkeypatch.setattr(context, "run_migrations", lambda: None)
    monkeypatch.setattr(sqlalchemy, "engine_from_config", capture_engine)
    runpy.run_path(str(Path(__file__).resolve().parents[1] / "migrations" / "env.py"))

    assert captured["params"]["password"] == password
    assert captured["params"]["host"] == "db"
    assert captured["params"]["user"] == "test@user"
    assert captured["params"]["database"] == "migration_probe"


@pytest.mark.parametrize(
    "scheme,allow_http,expected_session",
    [("https", False, 200), ("http", False, 401), ("http", True, 200)],
)
def test_production_cookie_session(monkeypatch, scheme, allow_http, expected_session):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ALLOW_INSECURE_HTTP", allow_http)
    with TestClient(app, base_url=f"{scheme}://deployment.example:8080") as client:
        payload = {"username": "deploy_user", "password": "deployment-test-pass"}
        assert client.post("/api/v1/auth/register", json=payload).status_code == 200
        response = client.post("/api/v1/auth/login", json=payload)
        assert response.status_code == 200
        for cookie in response.headers.get_list("set-cookie"):
            assert "HttpOnly" in cookie
            assert "SameSite=lax" in cookie
            assert ("Secure" in cookie) is (not allow_http)
        assert client.get("/api/v1/auth/session").status_code == expected_session
        if expected_session == 200:
            # 同源带端口写请求与刷新后的 Cookie 也必须可用。
            origin = {"Origin": f"{scheme}://deployment.example:8080"}
            assert client.post("/api/v1/auth/refresh", headers=origin).status_code == 200
            assert client.get("/api/v1/auth/session").status_code == 200
