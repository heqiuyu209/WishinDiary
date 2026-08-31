# app/routers/report.py
import logging

import pymysql
from fastapi import APIRouter, Depends, HTTPException, status
from app.core.database import get_db_connection
from app.routers.auth import get_current_user_id

router = APIRouter(prefix="/api", tags=["Report"])
logger = logging.getLogger(__name__)

@router.get("/report")
def get_health_report(user_id: int = Depends(get_current_user_id)):
    connection = None
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            # 查询真实的历史周期与平均统计
            cursor.execute("""
                SELECT COUNT(*) as total_cycles, AVG(cycle_length) as avg_length
                FROM cycles WHERE user_id = %s AND cycle_length IS NOT NULL
            """, (user_id,))
            stats = cursor.fetchone()

            total_cycles = stats['total_cycles'] if stats else 0
            avg_length = round(stats['avg_length'], 1) if stats and stats['avg_length'] else 28.0

            # 从 prediction_logs 真正计算 MAE 平均误差 (实际日期 vs 预测日期)
            cursor.execute("""
                SELECT AVG(ABS(DATEDIFF(actual_date, predicted_date))) as mae_error
                FROM prediction_logs
                WHERE user_id = %s AND actual_date IS NOT NULL AND predicted_date IS NOT NULL
            """, (user_id,))
            error_row = cursor.fetchone()
            real_mae = round(error_row['mae_error'], 1) if error_row and error_row['mae_error'] else None

            # 痛经级别聚合
            cursor.execute("""
                SELECT AVG(cramps_severity) as avg_cramps
                FROM daily_logs WHERE user_id = %s
            """, (user_id,))
            cramps_row = cursor.fetchone()
            avg_cramps = cramps_row['avg_cramps'] if cramps_row and cramps_row['avg_cramps'] else 0

            cramps_eval = "轻度微痛"
            if avg_cramps >= 2.0:
                cramps_eval = "重度剧痛"
            elif avg_cramps >= 1.0:
                cramps_eval = "中度疼痛"

            advice = {
                "轻度微痛": "保持规律作息与温和运动，持续记录症状变化。",
                "中度疼痛": "建议记录疼痛出现时间和持续时长；若反复影响生活，请咨询专业医务人员。",
                "重度剧痛": "如疼痛剧烈、持续或伴随异常出血，请及时就医；本摘要不能替代诊断。",
            }[cramps_eval]

            report_data = {
                "average_cycle_length": avg_length,
                "ai_prediction_accuracy_days": real_mae if real_mae is not None else "尚无对账样本",
                "total_recorded_cycles": total_cycles,
                "cramps_evaluation": cramps_eval,
                "doctor_advice_summary": advice,
                "disclaimer": "⚠️ 【免责声明】本应用预测结果基于统计学平滑与健康日志分析，仅供生活健康记录参考，不构成任何医疗诊断、临床治疗建议或避孕依据。"
            }
            return {"status": "success", "report": report_data}
    except pymysql.err.OperationalError:
        logger.exception("Report database connection failed for user_id=%s", user_id)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="数据库连接失败，请稍后重试")
    except Exception:
        logger.exception("report generation failed for user_id=%s", user_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="生成健康报告失败")
    finally:
        if connection is not None:
            connection.close()
