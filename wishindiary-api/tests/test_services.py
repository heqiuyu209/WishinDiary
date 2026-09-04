"""P1：service 层单元测试。

针对复杂业务规则做纯逻辑单测（不依赖真实数据库）：
- CycleService：周期开始/结束/更新的边界校验与重叠检测
- UserDataService：导出序列化与级联删除顺序
- PredictionService：数据不足时返回 insufficient_data

通过 monkeypatch 把 `transaction()`、repository 函数与 audit 替换为
内存 stub，保证测试聚焦业务规则本身、快速且可离线运行。
"""

from datetime import date

import pytest

from app.core.errors import AppError
from app.services.cycle_service import CycleService
from app.services.user_data_service import UserDataService


class _FakeCursor:
    """内存游标：记录 execute 调用，按 fixture 预置数据返回。

    同时支持 `with cursor:` 上下文管理器协议（与真实游标一致）。
    """

    def __init__(self, data=None):
        self.data = data or {}
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return 0

    def fetchone(self):
        return self.data.get("fetchone")

    def fetchall(self):
        return self.data.get("fetchall", [])


def _patch_transaction(monkeypatch, fake_cursor):
    """把 service 模块命名空间中的 transaction 替换为返回假连接的上下文管理器。

    注意：service 模块通过 `from app.core.database import transaction` 导入，
    名称已绑定到各 service 模块自身，必须 patch 目标模块而非 app.core.database。
    """
    from app.services import (
        cycle_service,
        daily_log_service,
        prediction_service,
        report_service,
        stats_service,
        user_data_service,
    )

    class _FakeConnection:
        def __init__(self):
            self.cursor_obj = fake_cursor

        def cursor(self):
            return self.cursor_obj

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class _Ctx:
        def __enter__(self):
            return _FakeConnection()

        def __exit__(self, *args):
            return False

    for mod in (
        cycle_service,
        daily_log_service,
        prediction_service,
        report_service,
        stats_service,
        user_data_service,
    ):
        if hasattr(mod, "transaction"):
            monkeypatch.setattr(mod, "transaction", lambda: _Ctx())


@pytest.fixture
def fake_cursor():
    return _FakeCursor()


class TestCycleServiceLogStart:
    def test_rejects_future_start_date(self, monkeypatch):
        from app.services import cycle_service as mod

        monkeypatch.setattr(mod, "audit", lambda *a, **k: None)
        _patch_transaction(monkeypatch, _FakeCursor())
        with pytest.raises(AppError) as exc_info:
            CycleService().log_start(1, date(2099, 1, 1))
        assert exc_info.value.status_code == 400

    def test_rejects_start_earlier_than_open_cycle(self, monkeypatch, fake_cursor):
        """存在进行中的周期时，新开始日期不能早于/等于上一个未结束周期。"""
        from app.services import cycle_service as mod

        fake_cursor.data["fetchone"] = {"cycle_id": 10, "start_date": date(2026, 8, 1)}
        monkeypatch.setattr(
            mod,
            "get_unclosed_cycle_for_update",
            lambda cursor, user_id: {"cycle_id": 10, "start_date": date(2026, 8, 1)},
        )
        monkeypatch.setattr(mod, "audit", lambda *a, **k: None)
        _patch_transaction(monkeypatch, fake_cursor)

        with pytest.raises(AppError) as exc_info:
            CycleService().log_start(1, date(2026, 8, 1))
        assert exc_info.value.status_code == 400
        assert "进行中的周期" in exc_info.value.message


class TestCycleServiceLogEnd:
    def test_rejects_end_earlier_than_start(self, monkeypatch, fake_cursor):
        from app.services import cycle_service as mod

        active = {"cycle_id": 1, "start_date": date(2026, 8, 1)}
        monkeypatch.setattr(
            mod,
            "get_cycle_for_log_end",
            lambda cursor, user_id, cycle_id=None: active,
        )
        monkeypatch.setattr(mod, "audit", lambda *a, **k: None)
        _patch_transaction(monkeypatch, fake_cursor)

        with pytest.raises(AppError) as exc_info:
            CycleService().log_end(1, date(2026, 7, 30))
        assert exc_info.value.status_code == 400
        assert "结束日期不能早于开始日期" in exc_info.value.message

    def test_rejects_future_end_date(self, monkeypatch):
        from app.services import cycle_service as mod

        monkeypatch.setattr(mod, "audit", lambda *a, **k: None)
        _patch_transaction(monkeypatch, _FakeCursor())
        with pytest.raises(AppError) as exc_info:
            CycleService().log_end(1, date(2099, 1, 1))
        assert exc_info.value.status_code == 400


class TestUserDataService:
    def test_export_user_not_found(self, monkeypatch, fake_cursor):
        from app.services import user_data_service as mod

        fake_cursor.data["fetchone"] = None
        _patch_transaction(monkeypatch, fake_cursor)
        monkeypatch.setattr(mod, "audit", lambda *a, **k: None)

        with pytest.raises(AppError) as exc_info:
            UserDataService().export_user_data(999)
        assert exc_info.value.status_code == 404

    def test_export_iso_serialization(self):
        """_iso 应把 date/datetime 统一转为 ISO 字符串。"""
        from datetime import datetime, timezone

        from app.services.user_data_service import _iso

        assert _iso(None) is None
        assert _iso(date(2026, 8, 1)) == "2026-08-01"
        assert (
            _iso(datetime(2026, 8, 1, 12, 30, tzinfo=timezone.utc))
            == "2026-08-01T12:30:00+00:00"
        )
        assert _iso("plain") == "plain"

    def test_delete_cascade_order(self, monkeypatch, fake_cursor):
        """级联删除应先子表后主表：prediction_logs → daily_logs → cycles → users。"""
        from app.services import user_data_service as mod

        fake_cursor.data["fetchone"] = {"user_id": 1}
        _patch_transaction(monkeypatch, fake_cursor)
        monkeypatch.setattr(mod, "audit", lambda *a, **k: None)

        result = UserDataService().delete_user_data(1)
        assert result["status"] == "success"

        sqls = [sql for sql, _ in fake_cursor.executed]
        del_sqls = [s for s in sqls if s.upper().startswith("DELETE")]
        assert any("prediction_logs" in s for s in del_sqls)
        assert any("daily_logs" in s for s in del_sqls)
        assert any("cycles" in s for s in del_sqls)
        assert any("users" in s for s in del_sqls)
        # 顺序断言：prediction_logs 必须在 users 之前
        assert del_sqls.index(next(s for s in del_sqls if "users" in s)) > del_sqls.index(
            next(s for s in del_sqls if "prediction_logs" in s)
        )


class TestPredictionService:
    def test_returns_insufficient_data_when_features_missing(self, monkeypatch):
        """特征提取抛 ValueError 时应返回 insufficient_data 而非 500。"""
        from app.services import prediction_service as mod

        def _raise_value_error(user_id):
            raise ValueError("历史数据不足，无法提取特征")

        monkeypatch.setattr(mod, "get_latest_features_for_user", _raise_value_error)

        from app.services.prediction_service import PredictionService

        result = PredictionService().get_prediction(1)
        assert result["status"] == "insufficient_data"
        assert "预测" in result["message"] or "数据不足" in result["message"]
