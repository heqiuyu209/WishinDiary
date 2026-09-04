"""Health report business logic（健康报告 service 层）。

将周期统计、预测误差（MAE）、痛经评估与建议生成的逻辑从路由下沉到本层，
统一使用 `with transaction()` 管理连接、AppError 表达可预期失败。
"""

import logging
import math

import pymysql

from app.core.database import transaction
from app.core.errors import AppError
from app.repositories import get_user_cycle_summary

logger = logging.getLogger(__name__)


class ReportService:
    """健康报告业务：周期统计、预测准确度与痛经评估。"""

    def get_report(self, user_id: int) -> dict:
        try:
            with transaction() as connection:
                with connection.cursor() as cursor:
                    # 周期总数与平均周期长度（统一走仓储层，避免 SQL 重复维护）
                    stats = get_user_cycle_summary(cursor, user_id)
                    total_cycles = stats["total_cycles"] if stats else 0
                    avg_length = (
                        round(stats["avg_cycle_length"], 1)
                        if stats and stats["avg_cycle_length"]
                        else 28.0
                    )

                    # AI 预测 MAE（实际日期 vs 预测日期）
                    cursor.execute(
                        """
                        SELECT AVG(ABS(DATEDIFF(actual_date, predicted_date))) AS mae_error
                        FROM prediction_logs
                        WHERE user_id = %s AND actual_date IS NOT NULL
                          AND predicted_date IS NOT NULL
                        """,
                        (user_id,),
                    )
                    error_row = cursor.fetchone()
                    real_mae = (
                        round(error_row["mae_error"], 1)
                        if error_row and error_row["mae_error"]
                        else None
                    )

                    # 痛经级别聚合
                    cursor.execute(
                        "SELECT AVG(cramps_severity) AS avg_cramps FROM daily_logs WHERE user_id = %s",
                        (user_id,),
                    )
                    cramps_row = cursor.fetchone()
                    avg_cramps = (
                        cramps_row["avg_cramps"]
                        if cramps_row and cramps_row["avg_cramps"]
                        else 0
                    )

                    cramps_eval = "轻度微痛"
                    if avg_cramps >= 2.0:
                        cramps_eval = "重度剧痛"
                    elif avg_cramps >= 1.0:
                        cramps_eval = "中度疼痛"

                    # 周期规律性：基于全部已记录周期长度的波动（标准差）评估
                    cursor.execute(
                        """
                        SELECT start_date, cycle_length
                        FROM cycles
                        WHERE user_id = %s AND cycle_length IS NOT NULL
                        ORDER BY start_date
                        """,
                        (user_id,),
                    )
                    cycle_rows = cursor.fetchall()
                    cycle_lengths = (
                        [r["cycle_length"] for r in cycle_rows] if cycle_rows else []
                    )

                    regularity = "记录样本不足"
                    if len(cycle_lengths) >= 3:
                        mean_len = sum(cycle_lengths) / len(cycle_lengths)
                        variance = sum(
                            (x - mean_len) ** 2 for x in cycle_lengths
                        ) / len(cycle_lengths)
                        std_dev = math.sqrt(variance)
                        if std_dev <= 2.0:
                            regularity = "规律"
                        elif std_dev <= 5.0:
                            regularity = "较规律"
                        else:
                            regularity = "波动较大"

                    # 最近一次预测对账（最靠近当前的实际日期 vs 当时预测）
                    cursor.execute(
                        """
                        SELECT predicted_date, actual_date,
                               ABS(DATEDIFF(actual_date, predicted_date)) AS abs_err
                        FROM prediction_logs
                        WHERE user_id = %s AND actual_date IS NOT NULL
                          AND predicted_date IS NOT NULL
                        ORDER BY actual_date DESC
                        LIMIT 1
                        """,
                        (user_id,),
                    )
                    latest_row = cursor.fetchone()
                    latest_err = (
                        latest_row["abs_err"]
                        if latest_row and latest_row["abs_err"] is not None
                        else None
                    )

                    # 记录充分度：样本越少越要提示谨慎解读
                    if total_cycles == 0:
                        readiness = "还没有完整的周期记录，建议持续打卡 2~3 个周期后再看，结论会更可靠。"
                    elif total_cycles < 3:
                        readiness = (
                            f"目前仅有 {total_cycles} 个周期记录，样本偏少，结论仅供参考。"
                        )
                    else:
                        readiness = "已有充足周期记录，以下结论相对可靠。"

                    # 平均周期区间提示（非诊断性参考）
                    if avg_length < 21:
                        length_hint = f"平均周期约 {avg_length} 天，偏短，常见范围是 21~35 天。"
                    elif avg_length <= 35:
                        length_hint = (
                            f"平均周期约 {avg_length} 天，处于常见范围（21~35 天）内。"
                        )
                    else:
                        length_hint = f"平均周期约 {avg_length} 天，偏长，常见范围是 21~35 天。"

                    advice = {
                        "轻度微痛": "保持规律作息与温和运动，持续记录症状变化。",
                        "中度疼痛": "建议记录疼痛出现时间和持续时长；若反复影响生活，请咨询专业医务人员。",
                        "重度剧痛": "如疼痛剧烈、持续或伴随异常出血，请及时就医；本摘要不能替代诊断。",
                    }[cramps_eval]

                    # 多维度组合建议：规律性 + 周期区间 + 样本充分度 + 痛经 + 对账反馈
                    advice_parts = [
                        f"周期规律性：{regularity}。",
                        length_hint,
                        readiness,
                        advice,
                    ]
                    if latest_err is not None:
                        advice_parts.append(
                            f"最近一次预测与实际相差 {latest_err} 天，误差越小说明推荐越贴合你的节奏。"
                        )
                    else:
                        advice_parts.append(
                            "每次经期结束后及时打卡，样本越多预测越准。"
                        )
                    doctor_advice = " ".join(advice_parts)

                    report_data = {
                        "average_cycle_length": avg_length,
                        "ai_prediction_accuracy_days": (
                            real_mae if real_mae is not None else "尚无对账样本"
                        ),
                        "total_recorded_cycles": total_cycles,
                        "cramps_evaluation": cramps_eval,
                        "doctor_advice_summary": doctor_advice,
                        "cycle_regularity": regularity,
                        "data_readiness": readiness,
                        "cycle_length_hint": length_hint,
                        "latest_prediction_error_days": (
                            latest_err if latest_err is not None else None
                        ),
                        "disclaimer": "⚠️ 【免责声明】本应用预测结果基于统计学平滑与健康日志分析，仅供生活健康记录参考，不构成任何医疗诊断、临床治疗建议或避孕依据。",
                    }
                    return {"status": "success", "report": report_data}
        except pymysql.err.OperationalError:
            logger.exception("Report database connection failed for user_id=%s", user_id)
            raise AppError(503, "service_unavailable", "数据库连接失败，请稍后重试")
        except AppError:
            raise
        except Exception:
            logger.exception("report generation failed for user_id=%s", user_id)
            raise AppError(500, "internal_error", "生成健康报告失败")
