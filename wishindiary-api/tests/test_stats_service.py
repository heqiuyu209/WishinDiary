"""P1：StatsService 单测（成功路径 + 异常兜底 500）。

对齐 pytest --cov 缺口的 stats_service（except Exception 分支未覆盖）。
"""

import pytest

from app.core.errors import AppError
from app.services.stats_service import StatsService


class _FakeCursor:
    """execute 可配置为抛异常，用于触发 service 的 500 兜底。"""

    def __init__(self, raise_on_execute=False):
        self._raise = raise_on_execute

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        if self._raise:
            raise RuntimeError("db boom")
        return 0

    def fetchall(self):
        return []


def _patch_transaction(monkeypatch, fake_cursor):
    from app.services import stats_service as mod

    class _FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def cursor(self):
            return fake_cursor

    class _Ctx:
        def __enter__(self):
            return _FakeConnection()

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(mod, "transaction", lambda: _Ctx())
    # stats_service 通过模块级 from-import 绑定了该函数引用，必须 patch service 命名空间
    monkeypatch.setattr(
        mod,
        "get_user_dashboard_data",
        lambda cursor, user_id: ([{"cycle_id": 1}], [{"log_id": 2}]),
    )


def test_get_stats_success(monkeypatch):
    fake = _FakeCursor()
    _patch_transaction(monkeypatch, fake)
    result = StatsService().get_stats(1)
    assert result["status"] == "success"
    assert result["cycles"] == [{"cycle_id": 1}]
    assert result["recent_logs"] == [{"log_id": 2}]


def test_get_stats_raises_unified_500_on_db_error(monkeypatch):
    from app.services import stats_service as mod

    fake = _FakeCursor()
    _patch_transaction(monkeypatch, fake)
    # 让底层查询抛任意异常，验证 service 统一兜底为 500 internal_error
    monkeypatch.setattr(
        mod, "get_user_dashboard_data", lambda cursor, user_id: (_ for _ in ()).throw(RuntimeError("db boom"))
    )
    with pytest.raises(AppError) as exc_info:
        StatsService().get_stats(1)
    assert exc_info.value.status_code == 500
    assert exc_info.value.code == "internal_error"
