"""Read-only research summaries; never return identifiable health records."""
import hashlib
import json
import logging
import math

from app.core.config import settings
from app.core.database import transaction
from app.core.errors import AppError

logger = logging.getLogger(__name__)


def read_evaluation_report() -> dict:
    path = settings.model_abs_path.parent / "model_evaluation_report.json"
    if not path.exists():
        return {"available": False, "message": "尚未生成离线评估报告"}
    try:
        if path.stat().st_size > 1_000_000:
            raise ValueError("Oversized evaluation report")
        report = json.loads(path.read_text(encoding="utf-8"))
        metadata = report.get("metadata", {})
        dataset = report.get("dataset", {})
        metrics = {}
        for protocol in ("holdout", "group_kfold", "temporal_holdout"):
            values = report.get(protocol, {})
            metrics[protocol] = {
                key: value for key, value in values.items()
                if key in {"mae", "rmse", "test_samples", "n_splits", "hit_rate_within_2d",
                           "hit_rate_within_3d", "baseline_mean3_mae", "baseline_mean3_hit3"}
                and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
            }
        digest = str(report.get("model_sha256", ""))[:64]
        model_matches = None
        if settings.model_abs_path.is_file() and digest:
            model_matches = hashlib.sha256(settings.model_abs_path.read_bytes()).hexdigest() == digest
        return {
            "available": True,
            "generated_at": str(metadata.get("generated_at", ""))[:40],
            "git_commit": str(metadata.get("git_commit", ""))[:40],
            "model_version": str(metadata.get("model_version", ""))[:80],
            "model_matches_report": model_matches,
            "dataset": {key: dataset.get(key) for key in (
                "source", "total_samples", "real_samples", "synthetic_samples", "n_users")},
            "metrics": metrics,
        }
    except (OSError, ValueError, TypeError, AttributeError):
        logger.warning("Research evaluation report could not be read")
        return {"available": False, "message": "评估报告无效，请重新生成"}


class ResearchService:
    def get_summary(self) -> dict:
        try:
            with transaction() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT COUNT(*) AS n FROM users")
                    users = int(cursor.fetchone()["n"])
                    cursor.execute("""
                        SELECT COUNT(*) AS total,
                          SUM(cycle_length IS NOT NULL) AS completed,
                          SUM(cycle_length IS NOT NULL AND cycle_length NOT BETWEEN 15 AND 45) AS outside_range,
                          SUM(cycle_length IS NOT NULL AND bleeding_days IS NULL) AS missing_bleeding
                        FROM cycles
                    """)
                    row = cursor.fetchone()
                    counts = {key: int(row[key] or 0) for key in row}
                    cursor.execute("""
                        SELECT cycle_length AS days, COUNT(*) AS count FROM cycles
                        WHERE cycle_length IS NOT NULL GROUP BY cycle_length ORDER BY cycle_length
                    """)
                    distribution = [{"days": int(r["days"]), "count": int(r["count"])} for r in cursor.fetchall()]
                    cursor.execute("""
                        SELECT u.user_id, COUNT(c.cycle_id) AS n FROM users u
                        LEFT JOIN cycles c ON c.user_id = u.user_id
                          AND c.cycle_length BETWEEN 15 AND 45
                          AND (c.bleeding_days IS NULL OR c.bleeding_days BETWEEN 1 AND 15)
                        GROUP BY u.user_id
                    """)
                    histories = [int(r["n"]) for r in cursor.fetchall()]
                    cursor.execute("SELECT state, COUNT(*) AS count FROM reminder_deliveries GROUP BY state ORDER BY state")
                    reminder_states = [{"state": r["state"], "count": int(r["count"])} for r in cursor.fetchall()]
        except Exception:
            logger.exception("Research data summary failed")
            raise AppError(503, "service_unavailable", "研究汇总暂不可用，请稍后重试")
        evaluation = read_evaluation_report()
        recommendations = []
        if evaluation.get("dataset", {}).get("source") == "synthetic":
            recommendations.append("当前指标来自合成数据，用于验证流程；真实预测效果需要独立授权数据评估。")
        group = evaluation.get("metrics", {}).get("group_kfold", {})
        if "mae" in group and "baseline_mean3_mae" in group:
            if group["mae"] >= group["baseline_mean3_mae"]:
                recommendations.append("随机森林尚未优于最近三次均值：先对比窗口长度、个人历史收缩、中位数与指数平滑。")
            else:
                recommendations.append("随机森林在当前分用户验证优于均值基线：继续用时间回测检查完整线上预测链路。")
        if counts["outside_range"] or counts["missing_bleeding"]:
            recommendations.append("存在范围外周期或缺失出血天数：核对记录来源，分别评估不同波动程度与缺失比例，保留原始记录。")
        if evaluation.get("model_matches_report") is False:
            recommendations.append("当前模型文件与评估报告不匹配，请生成对应报告后再解读指标。")
        recommendations.append("补充完整线上算法的前瞻回测、分组误差和预测区间覆盖率；离线 RF 指标不能直接代表最终提醒效果。")
        return {
            "status": "success",
            "data": {
                "users": users, **counts,
                "users_with_ml_history": sum(n >= 4 for n in histories),
                "feature_samples": sum(max(0, n - 3) for n in histories),
                "cycle_distribution": distribution,
                "reminder_states": reminder_states,
                "history_distribution": [
                    {"label": "0 条", "count": sum(n == 0 for n in histories)},
                    {"label": "1–3 条", "count": sum(1 <= n < 4 for n in histories)},
                    {"label": "4–7 条", "count": sum(4 <= n < 8 for n in histories)},
                    {"label": "8 条以上", "count": sum(n >= 8 for n in histories)},
                ],
            },
            "evaluation": evaluation,
            "recommendations": recommendations,
        }
