"""P0 安全：Token 过期/刷新/撤销/退出登录策略 + 数据修改审计日志测试。"""

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.core import database


def _register_and_login(client: TestClient, username: str, password: str = "password123"):
    assert client.post(
        "/api/v1/auth/register", json={"username": username, "password": password}
    ).status_code == 200
    login = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert login.status_code == 200, login.text
    return login


def _insert_expired_refresh_token(user_id: int) -> str:
    """直接向 DB 插入一条已过期的 refresh token，返回明文用于构造 Cookie。"""
    import secrets

    plain = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(plain.encode("utf-8")).hexdigest()
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
    conn = database.get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO refresh_tokens (user_id, token_hash, expires_at) VALUES (%s, %s, %s)",
                (user_id, token_hash, expires_at),
            )
        conn.commit()
    finally:
        conn.close()
    return plain


def test_login_sets_httponly_refresh_cookie(client):
    """P0 安全：登录同时下发短期 access_token 与长期 refresh_token 两个 HttpOnly Cookie。"""
    response = _register_and_login(client, "refresh_setup_user")
    set_cookie = response.headers.get("set-cookie", "")
    assert "refresh_token=" in set_cookie
    assert "HttpOnly" in set_cookie
    # 响应体依旧不泄露任何 JWT
    assert "access_token" not in response.json()
    assert client.cookies.get("refresh_token")


def test_refresh_rotates_token_and_revokes_old(client):
    """P0 安全：/refresh 用旧 refresh token 换新 access + 新 refresh，且旧 token 被服务端撤销。"""
    _register_and_login(client, "rotate_user")
    old_refresh = client.cookies.get("refresh_token")
    assert old_refresh

    res = client.post("/api/v1/auth/refresh")
    assert res.status_code == 200, res.text
    assert res.json()["user_id"] >= 1
    # 轮换：refresh cookie 已替换为新值
    new_refresh = client.cookies.get("refresh_token")
    assert new_refresh and new_refresh != old_refresh
    # 新 access token 立即可用
    assert client.get("/api/v1/auth/session").status_code == 200

    # 重放旧 refresh token 必须被拒（服务端已撤销）
    replay = client.post(
        "/api/v1/auth/refresh", headers={"Cookie": f"refresh_token={old_refresh}"}
    )
    assert replay.status_code == 401


def test_refresh_without_token_rejected(client):
    """P0 安全：未携带 refresh token 的刷新请求被拒绝。"""
    client.post("/api/v1/auth/refresh")
    # 清空本地 Cookie 后再次刷新
    client.cookies.clear()
    res = client.post("/api/v1/auth/refresh")
    assert res.status_code == 401


def test_refresh_rejects_expired_token(client):
    """P0 安全：过期的 refresh token 拒绝续期。"""
    login = _register_and_login(client, "expired_refresh_user")
    user_id = login.json()["user_id"]
    expired = _insert_expired_refresh_token(user_id)
    res = client.post(
        "/api/v1/auth/refresh", headers={"Cookie": f"refresh_token={expired}"}
    )
    assert res.status_code == 401


def test_logout_revokes_refresh_and_clears_cookies(client):
    """P0 安全：退出登录后 refresh token 被服务端撤销，且两个 Cookie 均被清除。"""
    _register_and_login(client, "logout_user")
    refresh = client.cookies.get("refresh_token")
    assert refresh

    res = client.post("/api/v1/auth/logout")
    assert res.status_code == 200
    # Cookie 已被清除
    assert client.cookies.get("refresh_token") in (None, "")
    assert client.cookies.get("access_token") in (None, "")
    # 即便手动重放旧 refresh token，服务端也应拒绝（已撤销）
    replay = client.post(
        "/api/v1/auth/refresh", headers={"Cookie": f"refresh_token={refresh}"}
    )
    assert replay.status_code == 401


def test_logout_after_access_expiry_still_revokes(client):
    """P0 安全：access token 过期后，仅凭 refresh token 也能完成服务端撤销登出。"""
    _register_and_login(client, "late_logout_user")
    refresh = client.cookies.get("refresh_token")
    res = client.post("/api/v1/auth/logout", headers={"Cookie": f"refresh_token={refresh}"})
    assert res.status_code == 200
    replay = client.post(
        "/api/v1/auth/refresh", headers={"Cookie": f"refresh_token={refresh}"}
    )
    assert replay.status_code == 401


class _AuditLogRecorder(logging.Handler):
    """将审计 logger 的 record 捕获到内存列表。

    说明：alembic 运行（dictConfig/fileConfig）默认会把已存在的 logger
    disabled=True，因此本类在挂载时会显式恢复 ``disabled`` 与级别，
    不依赖 pytest caplog 的 root 挂载机制。
    """

    def __init__(self):
        super().__init__(level=logging.INFO)
        self.records: list[logging.LogRecord] = []
        self._logger = logging.getLogger("wishindiary.audit")

    def __enter__(self):
        self._logger.disabled = False
        self._logger.setLevel(logging.INFO)
        self._logger.addHandler(self)
        return self

    def __exit__(self, *_exc):
        self._logger.removeHandler(self)

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    @property
    def actions(self) -> list[str]:
        return [json.loads(rec.getMessage())["action"] for rec in self.records]


def test_audit_log_written_on_data_modification(client):
    """P0 安全：周期数据修改（log_start）写入结构化审计日志。"""
    _register_and_login(client, "audit_data_user")
    with _AuditLogRecorder() as captured:
        res = client.post("/api/v1/log_start", json={"start_date": "2026-07-01"})
        assert res.status_code == 200, res.text
    assert "cycle.log_start" in captured.actions


def test_audit_log_written_on_account_delete(client):
    """P0 安全：删除账号（敏感操作）写入结构化审计日志。"""
    _register_and_login(client, "audit_delete_user")
    with _AuditLogRecorder() as captured:
        res = client.delete("/api/v1/user/me")
        assert res.status_code == 200, res.text
    assert "user_data.delete" in captured.actions
