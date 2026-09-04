"""A 类隐私改造测试：监控事件不落 user_id + 按天分片 + 保留期清理。

所有用例将落盘目录重定向到 pytest 临时目录，不污染真实 monitoring_logs。
"""

import json
import os
import time
from datetime import datetime, timezone

import pytest

from app.core.config import settings
from app.ml import monitoring


def _today_slice_name() -> str:
    return f"prediction_events-{datetime.now(timezone.utc).strftime('%Y%m%d')}.jsonl"


@pytest.fixture
def monitor_dir(tmp_path, monkeypatch):
    """把监控落盘目录与清理缓存重定向到临时目录。"""
    monkeypatch.setattr(monitoring, "MONITOR_DIR", tmp_path)
    monkeypatch.setattr(monitoring, "_last_cleanup_day", None)
    return tmp_path


def test_record_prediction_event_contains_no_user_id(monitor_dir):
    """落盘事件不得包含 user_id，且保留特征/预测摘要字段。"""
    monitoring.record_prediction(
        user_id=42,
        features={"age": 30.0, "avg_cycle": 28.7},
        prediction={
            "predicted_cycle_length": 29,
            "raw_predicted_cycle_length": 28.9,
            "confidence_interval": [27.0, 30.0],
            "next_period_start": "2026-09-15",
        },
        model_version="rf-v2",
    )
    slice_path = monitor_dir / _today_slice_name()
    assert slice_path.exists(), "应按天生成分片文件"
    events = [
        json.loads(line)
        for line in slice_path.read_text(encoding="utf-8").strip().splitlines()
    ]
    assert len(events) == 1
    event = events[0]
    assert "user_id" not in event, "事件不得包含 user_id"
    assert event["type"] == "prediction"
    assert event["model_version"] == "rf-v2"
    assert event["features"] == {"age": 30.0, "avg_cycle": 28.7}
    assert event["predicted_cycle_length"] == 29


def test_record_prediction_user_id_never_leaks_even_large(monitor_dir):
    """任意 user_id 都不会出现在落盘内容中（隐私设计与调用方无关）。"""
    monitoring.record_prediction(
        user_id=99999,
        features={"temp": 1.0},
        prediction={"predicted_cycle_length": 30},
        model_version="v1",
    )
    event_text = (monitor_dir / _today_slice_name()).read_text(encoding="utf-8")
    assert "99999" not in event_text
    assert "user_id" not in event_text


def test_list_prediction_event_files_sorted_across_slices(monitor_dir):
    """跨多分片时 list_prediction_event_files 按日期升序返回全部。"""
    (monitor_dir / "prediction_events-20260101.jsonl").write_text("{}\n", encoding="utf-8")
    (monitor_dir / "prediction_events-20260103.jsonl").write_text("{}\n", encoding="utf-8")
    (monitor_dir / "prediction_events-20260102.jsonl").write_text("{}\n", encoding="utf-8")
    names = [p.name for p in monitoring.list_prediction_event_files()]
    assert names == [
        "prediction_events-20260101.jsonl",
        "prediction_events-20260102.jsonl",
        "prediction_events-20260103.jsonl",
    ]


def test_cleanup_removes_expired_slices_keeps_recent(monitor_dir, monkeypatch):
    """超过 MONITOR_RETENTION_DAYS 的分片被删，保留期内的保留。"""
    monkeypatch.setattr(settings, "MONITOR_RETENTION_DAYS", 10)
    very_old = monitor_dir / "prediction_events-20250101.jsonl"  # ~400 天前
    old = monitor_dir / "prediction_events-20260101.jsonl"        # ~30 天前
    recent = monitor_dir / "prediction_events-20260601.jsonl"     # ~2 天前
    for p in (very_old, old, recent):
        p.write_text("{}\n", encoding="utf-8")
    now = time.time()
    os.utime(very_old, (now - 400 * 86400, now - 400 * 86400))
    os.utime(old, (now - 30 * 86400, now - 30 * 86400))
    os.utime(recent, (now - 2 * 86400, now - 2 * 86400))

    monitoring._cleanup_expired_event_files()

    remaining = {p.name for p in monitoring.list_prediction_event_files()}
    assert "prediction_events-20250101.jsonl" not in remaining
    assert "prediction_events-20260101.jsonl" not in remaining
    assert "prediction_events-20260601.jsonl" in remaining


def test_cleanup_zero_retention_keeps_all(monitor_dir, monkeypatch):
    """MONITOR_RETENTION_DAYS=0 表示永久保留，不删除任何分片。"""
    monkeypatch.setattr(settings, "MONITOR_RETENTION_DAYS", 0)
    old = monitor_dir / "prediction_events-20250101.jsonl"
    old.write_text("{}\n", encoding="utf-8")
    now = time.time()
    os.utime(old, (now - 365 * 86400, now - 365 * 86400))

    monitoring._cleanup_expired_event_files()

    assert old.exists(), "永久保留模式下旧分片不应被清理"
