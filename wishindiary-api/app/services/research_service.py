"""Read-only research summaries; never return identifiable health records."""
import hashlib
import json
import logging
import math

from app.core.config import settings
from app.core.database import transaction
from app.core.errors import AppError
from app.services.forecast_report_service import read_forecast_report

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
        forecast = read_forecast_report()
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
        if not forecast.get("available"):
            recommendations.append("生成完整流程的前瞻回测报告，比较个人历史收缩后的结果、简单基线、分组误差和区间覆盖率。")
        elif forecast.get("pipeline_matches_report") is False:
            recommendations.append("预测算法代码与回测报告不匹配，请重新生成报告后再比较结果。")
        else:
            if forecast["dataset"]["source"] == "synthetic":
                recommendations.append("完整流程回测也来自合成数据：只能验证研究流程，真实效果仍需要独立授权数据。")
            for name, label in (("existing_users", "既有用户"), ("unseen_users", "模型未见用户")):
                result = forecast["protocols"][name]
                methods = result["models"]
                point = methods.get("online_pipeline", {}).get("mae")
                baselines = [methods[key]["mae"] for key in ("mean3", "median3", "ewma")
                             if "mae" in methods.get(key, {})]
                if point is not None and baselines and point >= min(baselines):
                    recommendations.append(f"{label}回测中完整流程尚未超过最好的简单基线：比较个人历史权重和窗口长度，并用独立未来数据复核。")
                interval = result["intervals"].get("rf_personalized", {})
                coverage = interval.get("coverage_pct")
                calibration = result.get("calibration")
                if calibration:
                    recommendations.append(f"{label}已建立独立时间校准实验：同时比较覆盖率与区间宽度，用新的授权时间段复核，避免根据当前测试结果反复选择参数。")
                    for method, method_label in (("rf_personalized", "RF"), ("basic_stats", "基础统计")):
                        calibrated = calibration["methods"][method]
                        if calibrated["unavailable_samples"]:
                            recommendations.append(f"{label}的{method_label}路径有 {calibrated['unavailable_samples']} 条测试样本缺少足够校准历史：补充该路径的已完成校准周期，不与另一条路径混合。")
                        measured = calibrated["calibrated"].get("coverage_pct")
                        if measured is not None and measured < calibration["target_coverage_pct"]:
                            recommendations.append(f"{label}的{method_label}校准区间覆盖率为 {measured:.2f}%，低于实验目标：研究时间变化、用户差异与波动分组，在新的测试段复核。")
                        windows = [window["interval_comparison"][method]["calibrated"]
                                   for window in result.get("time_windows", [])
                                   if window["interval_comparison"][method]["calibrated"]["samples"]]
                        below = sum(window["coverage_pct"] < calibration["target_coverage_pct"] for window in windows)
                        if len(windows) > 1 and below:
                            recommendations.append(f"{label}的{method_label}有 {below}/{len(windows)} 个可评估时间窗的覆盖率低于实验目标：结合各窗样本量、波动和缺失分组检查，在预先固定的新时间段复核；分窗结果仅供探索，勿用同一测试集反复调参。")
                elif coverage is not None and coverage < 90:
                    recommendations.append(f"{label}的树分位区间覆盖率为 {coverage:.2f}%：优先建立独立时间校准段，再在未使用的未来测试段验证覆盖率与宽度。")
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
            "forecast_evaluation": forecast,
            "recommendations": recommendations,
        }
