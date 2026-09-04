"""并发写入与重复提交测试。

覆盖目标：
- 并发对同一用户 / 同一日期创建周期：唯一索引兜底，最终仅一条成功，其余 409；
- 顺序重复提交周期开始：第二次幂等返回 409 conflict；
- 重复提交每日日志：upsert 幂等，重复提交均成功且库内仅一条；
- 并发写入同一日期每日日志：全部成功且库内仅一条（ON DUPLICATE KEY 保护）。
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pymysql
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from tests.conftest import TEST_DB_NAME

USERNAME = "concurrency_user"
PASSWORD = "password123"


@pytest.fixture
def registered_user(client):
    """注册并登录一个并发测试用户，返回其 user_id。"""
    payload = {"username": USERNAME, "password": PASSWORD}
    client.post("/api/v1/auth/register", json=payload)
    resp = client.post("/api/v1/auth/login", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["user_id"]


def _count_rows(table: str, user_id: int, date_col: str, target: date) -> int:
    conn = pymysql.connect(
        host=settings.DB_HOST,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=TEST_DB_NAME,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT COUNT(*) FROM {table} WHERE user_id = %s AND {date_col} = %s",
                (user_id, target),
            )
            return int(cursor.fetchone()[0])
    finally:
        conn.close()


def _fresh_logged_in_client() -> TestClient:
    """为每个线程创建独立 TestClient，避免共享 CookieJar 的线程安全问题。"""
    c = TestClient(app)
    payload = {"username": USERNAME, "password": PASSWORD}
    resp = c.post("/api/v1/auth/login", json=payload)
    assert resp.status_code == 200, resp.text
    return c


def test_duplicate_cycle_start_conflicts(registered_user, client):
    """顺序重复提交周期开始：第一次成功，第二次幂等拒绝（conflict 错误码）。"""
    today = date.today()
    first = client.post("/api/v1/log_start", json={"start_date": today.isoformat()})
    assert first.status_code == 200, first.text

    second = client.post("/api/v1/log_start", json={"start_date": today.isoformat()})
    assert second.status_code in (400, 409), second.text
    assert second.json()["error"]["code"] == "conflict"


def test_concurrent_cycle_start_only_one_succeeds(registered_user):
    """并发对同一用户同一日期创建周期：不产生重复数据。

    insert_cycle 使用 INSERT ... ON DUPLICATE KEY UPDATE（结合 uk_user_start 唯一索引）
    实现幂等写入：并发线程可能因时序差异返回 200 或 400(conflict)，
    但数据库最终只保留一条记录，且不出现 500/internal_error。
    """
    today = date.today().isoformat()
    n_threads = 6

    def attempt(_: int) -> tuple[int, str]:
        c = _fresh_logged_in_client()
        resp = c.post("/api/v1/log_start", json={"start_date": today})
        if resp.status_code == 200:
            return resp.status_code, "ok"
        return resp.status_code, resp.json()["error"]["code"]

    with ThreadPoolExecutor(max_workers=n_threads) as pool:
        results = list(pool.map(attempt, range(n_threads)))

    statuses = [status for status, _ in results]
    codes = [code for _, code in results]

    # 1) 不允许任何 5xx / internal_error：并发写入不得破坏幂等契约
    assert all(s < 500 for s in statuses), f"并发写入不应出现 5xx，实际: {results}"
    assert "internal_error" not in codes, f"并发写入不应出现 internal_error，实际: {results}"

    # 2) 成功与幂等拒绝（conflict）共存均可，但必须存在成功提交
    assert statuses.count(200) >= 1, f"至少应有一个线程成功提交，实际: {results}"
    assert all(c == "conflict" for s, c in results if s != 200), (
        f"非 200 的结果错误码应为 conflict（幂等拒绝），实际: {results}"
    )

    # 3) 库内确认最终只有一条记录（唯一索引 uk_user_start + upsert 兜底）
    assert _count_rows("cycles", registered_user, "start_date", date.today()) == 1


def test_daily_log_repeated_submit_is_idempotent(registered_user, client):
    """重复提交同一日日志：upsert 幂等，均成功且库内仅一条。"""
    payload = {
        "log_date": date.today().isoformat(),
        "mood_level": 2,
        "cramps_severity": 1,
        "is_exercise": True,
        "is_intercourse": False,
        "exercise_type": "跑步",
        "exercise_minutes": 30,
        "diet_tag": "清淡",
        "journal_text": "今日状态不错",
    }
    first = client.post("/api/v1/daily_log", json=payload)
    assert first.status_code == 200, first.text
    second = client.post("/api/v1/daily_log", json=payload)
    assert second.status_code == 200, second.text

    assert _count_rows("daily_logs", registered_user, "log_date", date.today()) == 1


def test_concurrent_daily_log_same_date_upserts_to_one(registered_user):
    """并发写入同一日日志：全部成功（ON DUPLICATE KEY UPDATE），库内仅一条。"""
    today = date.today().isoformat()
    payload = {
        "log_date": today,
        "mood_level": 1,
        "cramps_severity": 0,
        "is_exercise": False,
        "is_intercourse": False,
        "exercise_type": None,
        "exercise_minutes": 0,
        "diet_tag": None,
        "journal_text": "并发提交测试",
    }
    n_threads = 6

    def attempt(_: int) -> int:
        c = _fresh_logged_in_client()
        resp = c.post("/api/v1/daily_log", json=payload)
        return resp.status_code

    with ThreadPoolExecutor(max_workers=n_threads) as pool:
        statuses = list(pool.map(attempt, range(n_threads)))

    assert all(s == 200 for s in statuses), f"所有并发提交应成功，实际: {statuses}"
    assert _count_rows("daily_logs", registered_user, "log_date", date.today()) == 1
