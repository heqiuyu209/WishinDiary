"""
模型监控汇总脚本 — 汇总推理输入分布与预测误差。

输入来源：
1. `ml/monitoring_logs/prediction_events-*.jsonl` — 每次推理记录的特征快照与预测结果
   （在线生成，按天分片；事件不落用户维度，见 app/ml/monitoring.py 隐私设计）
2. 数据库 `prediction_logs` 表 — /log_start 回填的 actual_date/error_days，用于计算真实预测误差

用法: python scripts/monitor_model.py  (从 wishindiary-api 目录运行)
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from app.core.database import get_db_connection
from app.ml.monitoring import list_prediction_event_files
from app.ml.contract import FEATURE_NAMES


def load_prediction_events() -> pd.DataFrame:
    """读取在线推理监控事件（JSONL，跨全部按天分片合并）。"""
    rows = []
    for path in list_prediction_event_files():
        try:
            with path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            continue
    return pd.DataFrame(rows)


def summarize_input_distribution(events: pd.DataFrame) -> pd.DataFrame:
    """汇总各输入特征的分布统计（均值/标准差/最小/最大/样本量）。"""
    if events.empty:
        return pd.DataFrame()
    features_df = events["features"].apply(pd.Series)
    missing = [f for f in FEATURE_NAMES if f not in features_df.columns]
    for f in missing:
        features_df[f] = float("nan")
    features_df = features_df[list(FEATURE_NAMES)]
    summary = pd.DataFrame({
        "mean": features_df.mean(),
        "std": features_df.std(),
        "min": features_df.min(),
        "max": features_df.max(),
        "count": features_df.count(),
    })
    return summary


def summarize_prediction_error() -> dict:
    """从 prediction_logs 读取已回填的真实误差，计算 MAE / RMSE / 命中率。"""
    connection = None
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT predicted_date, actual_date, error_days
                FROM prediction_logs
                WHERE actual_date IS NOT NULL AND error_days IS NOT NULL
                ORDER BY created_at ASC
            """)
            rows = cursor.fetchall()
        if not rows:
            return {"samples": 0, "mae": None, "rmse": None, "hit_rate_plus_minus_3": None}
        errors = [abs(int(r["error_days"])) for r in rows]
        import math

        mae = sum(errors) / len(errors)
        rmse = math.sqrt(sum(e * e for e in errors) / len(errors))
        hit_rate = sum(1 for e in errors if e <= 3) / len(errors)
        return {
            "samples": len(errors),
            "mae": round(mae, 2),
            "rmse": round(rmse, 2),
            "hit_rate_plus_minus_3": round(hit_rate, 4),
        }
    except Exception as exc:
        return {"error": str(exc)}
    finally:
        if connection is not None:
            connection.close()


def main():
    events = load_prediction_events()
    print("=" * 50)
    print("📊 WishinDiary 模型监控汇总")
    print("=" * 50)

    if events.empty:
        print("\nℹ️ 暂无在线推理事件（ml/monitoring_logs/prediction_events-*.jsonl 为空）。")
    else:
        print(f"\n🟢 在线推理事件数: {len(events)}")
        summary = summarize_input_distribution(events)
        print("\n【输入特征分布】")
        print(summary.to_string(float_format=lambda v: f"{v:.4f}"))
        print("\n【模型版本分布】")
        if "model_version" in events.columns:
            print(events["model_version"].value_counts().to_string())
        ci = events["confidence_interval"].dropna()
        if not ci.empty:
            lows = [float(x["low"]) for x in ci if isinstance(x, dict)]
            highs = [float(x["high"]) for x in ci if isinstance(x, dict)]
            if lows:
                import statistics

                print("\n【置信区间统计（天）】")
                print(f"  平均下界: {statistics.mean(lows):.2f}  平均上界: {statistics.mean(highs):.2f}")

    print("\n【预测误差（基于 prediction_logs 回填）】")
    err = summarize_prediction_error()
    if "error" in err:
        print(f"  ⚠️ 查询失败: {err['error']}")
    elif err["samples"] == 0:
        print("  ℹ️ 暂无已回填的预测误差记录（等用户记录下一次经期开始后自动回填）。")
    else:
        print(f"  样本量: {err['samples']}")
        print(f"  MAE: {err['mae']} 天")
        print(f"  RMSE: {err['rmse']} 天")
        print(f"  ±3 天命中率: {err['hit_rate_plus_minus_3'] * 100:.1f}%")
    print("\n" + "=" * 50)


if __name__ == "__main__":
    main()
