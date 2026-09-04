"""轻量模型监控模块。

将每次推理的输入特征分布与预测结果以结构化 JSON 行落盘（JSONL），
配合 `scripts/monitor_model.py` 汇总输入特征统计与预测误差，
用于观测输入漂移与模型质量退化。不引入数据库表，
避免与 Alembic 迁移（migrations/versions/）重复维护数据库结构。

隐私设计：
- 事件不落任何用户维度（user_id），仅保留群体级输入分布与预测结果，
  不在磁盘留下可关联身份的标识，也无需维护用于匿名化的盐
  （固定盐 + 短哈希可被暴力枚举还原，反而引入隐患）。
- 事件按天分片存储（prediction_events-YYYYMMDD.jsonl），通过
  MONITOR_RETENTION_DAYS 控制保留天数，写入时惰性清理过期分片（默认 90 天）。
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MONITOR_DIR = PROJECT_ROOT / "ml" / "monitoring_logs"
PREDICTION_EVENTS_GLOB = "prediction_events-*.jsonl"

monitor_logger = logging.getLogger("wishindiary.monitor")

# 清理节点流：同一天只执行一次保留期清理，避免每次推理都扫描目录
_last_cleanup_day: str | None = None


def list_prediction_event_files() -> list[Path]:
    """返回全部预测事件分片（按日期升序）。"""
    return sorted(MONITOR_DIR.glob(PREDICTION_EVENTS_GLOB))


def _current_slice_path() -> Path:
    MONITOR_DIR.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return MONITOR_DIR / f"prediction_events-{day}.jsonl"


def _cleanup_expired_event_files() -> None:
    """删除超过 MONITOR_RETENTION_DAYS 保留期的旧分片（0 = 永久保留）。"""
    global _last_cleanup_day
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    if _last_cleanup_day == today:
        return
    _last_cleanup_day = today

    retention_days = settings.MONITOR_RETENTION_DAYS
    if retention_days <= 0:
        return
    try:
        cutoff = time.time() - retention_days * 86400
        for path in list_prediction_event_files():
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    monitor_logger.info("清理过期监控分片: %s", path.name)
            except OSError:
                continue
    except Exception:
        # 清理失败绝不能影响监控写入或核心推理链路
        monitor_logger.exception("清理过期监控分片失败")


def record_prediction(
    *,
    user_id: int | None,
    features: dict[str, float],
    prediction: dict[str, Any],
    model_version: str,
) -> None:
    """记录一次推理事件：输入特征快照 + 预测结果 + 置信区间。

    user_id 参数仅保留以兼容调用方签名，实际不落盘
    （见模块 docstring 隐私设计）。
    """
    try:
        path = _current_slice_path()
        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "prediction",
            "model_version": model_version,
            "features": {k: round(float(v), 4) for k, v in features.items()},
            "predicted_cycle_length": prediction.get("predicted_cycle_length"),
            "raw_predicted_cycle_length": prediction.get("raw_predicted_cycle_length"),
            "confidence_interval": prediction.get("confidence_interval"),
            "next_period_start": prediction.get("next_period_start"),
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    except Exception:
        # 监控失败绝不能影响核心推理链路
        monitor_logger.exception("记录模型监控事件失败")
        return

    # 写盘成功后再触发（尽力而为）的保留期清理
    _cleanup_expired_event_files()
