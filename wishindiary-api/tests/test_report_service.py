"""P1：ReportService 单测（覆盖痛经分级与空数据默认值分支）。

对齐 pytest --cov 缺口的 report_service：
- avg_cramps >= 2.0 → 重度剧痛
- 1.0 <= avg_cramps < 2.0 → 中度疼痛
- 无数据默认：平均周期 28.0、MAE 显示"尚无对账样本"、轻度微痛
- real_mae / avg_length 非空时的数值回显
使用假的排队游标逐次返回三条查询结果（stats → MAE → cramps）。
"""


from app.services.report_service import ReportService


class _FakeCursor:
    """按查询顺序逐条返回预置结果（fetchone 队列）。"""

    def __init__(self, queue):
        self._queue = list(queue)
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self.executed.append(sql)
        return 0

    def fetchone(self):
        if not self._queue:
            return None
        return self._queue.pop(0)

    def fetchall(self):
        return []


def _patch_transaction(monkeypatch, fake_cursor):
    from app.services import report_service as mod

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


def _run(monkeypatch, queue) -> dict:
    fake_cursor = _FakeCursor(queue)
    _patch_transaction(monkeypatch, fake_cursor)
    return ReportService().get_report(1)


class TestReportCrampsEvaluation:
    def test_severe_when_avg_cramps_ge_2(self, monkeypatch):
        report = _run(
            monkeypatch,
            [
                {"total_cycles": 3, "avg_cycle_length": 29.4},
                {"mae_error": 6.2},
                {"avg_cramps": 2.5},
            ],
        )
        assert report["report"]["cramps_evaluation"] == "重度剧痛"
        assert report["report"]["average_cycle_length"] == 29.4
        assert report["report"]["ai_prediction_accuracy_days"] == 6.2
        assert "及时就医" in report["report"]["doctor_advice_summary"]
        assert report["report"]["total_recorded_cycles"] == 3

    def test_moderate_when_avg_cramps_between_1_and_2(self, monkeypatch):
        report = _run(
            monkeypatch,
            [
                {"total_cycles": 1, "avg_cycle_length": 28.0},
                {"mae_error": None},
                {"avg_cramps": 1.5},
            ]
        )
        assert report["report"]["cramps_evaluation"] == "中度疼痛"
        assert report["report"]["ai_prediction_accuracy_days"] == "尚无对账样本"
        assert "咨询专业医务人员" in report["report"]["doctor_advice_summary"]

    def test_mild_when_no_data(self, monkeypatch):
        # AVG 查询对无行返回 None → 走默认分支（28.0 / 轻度微痛 / 尚无对账样本）
        report = _run(monkeypatch, [None, None, None])
        p = report["report"]
        assert p["average_cycle_length"] == 28.0
        assert p["total_recorded_cycles"] == 0
        assert p["cramps_evaluation"] == "轻度微痛"
