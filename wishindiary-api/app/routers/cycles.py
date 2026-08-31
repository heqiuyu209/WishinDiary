import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from datetime import date, datetime
import pymysql
from app.core.database import get_db_connection
from app.routers.auth import get_current_user_id
from app.features import get_latest_features_for_user
from app.schemas.prediction import PredictionResponse
from app.schemas.cycle import CycleUpdateRequest
from app.services.cycle_prediction_service import CyclePredictionService
from app.repositories import (
    get_cycle_by_id,
    update_cycle_dates,
    delete_cycle,
    recalculate_cycle_lengths,
)

router = APIRouter(prefix="/api", tags=["Cycles"])
logger = logging.getLogger(__name__)

# 复用离线预训练模型（应用启动时加载一次，请求时只做推理，不重训）
_prediction_service = CyclePredictionService()


def _normalize_date(value):
    """兼容数据库返回的 date / datetime / str。"""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return datetime.strptime(value, "%Y-%m-%d").date()
    return value


class LogStartRequest(BaseModel):
    start_date: date


class LogEndRequest(BaseModel):
    end_date: date
    cycle_id: int | None = None

@router.post("/log_start")
def log_start(req: LogStartRequest, user_id: int = Depends(get_current_user_id)):
    start_date = req.start_date
    if start_date > date.today():
        raise HTTPException(status_code=400, detail="开始日期不能晚于今天")
    connection = get_db_connection()

    try:
        connection.begin()  # 显式开启事务
        with connection.cursor() as cursor:
            # 1. 行级排他锁，防止并发读写
            cursor.execute("""
                           SELECT cycle_id, start_date
                           FROM cycles
                           WHERE user_id = %s
                             AND end_date IS NULL
                           ORDER BY start_date DESC
                           LIMIT 1
                               FOR UPDATE
                           """, (user_id,))
            unclosed_cycle = cursor.fetchone()

            if unclosed_cycle:
                prev_start = unclosed_cycle['start_date']
                if isinstance(prev_start, str):
                    prev_start = datetime.strptime(prev_start, "%Y-%m-%d").date()

                # 如果开启的新周期时间早于未闭合周期，拒绝异常写入
                if start_date <= prev_start:
                    connection.rollback()
                    raise HTTPException(
                        status_code=400,
                        detail="存在进行中的周期：新周期开始日期不能早于或等于上个未结束周期",
                    )

                cycle_length = (start_date - prev_start).days
                bleeding_days = 5  # 缺省流血天数

                # 闭合上一周期
                cursor.execute("""
                               UPDATE cycles
                               SET end_date      = %s,
                                   cycle_length  = %s,
                                   bleeding_days = %s
                               WHERE cycle_id = %s
                               """, (start_date, cycle_length, bleeding_days, unclosed_cycle['cycle_id']))

            # 2. 写入新周期 (利用 UNIQUE KEY uk_user_start 兜底幂等性)
            cursor.execute("""
                           INSERT INTO cycles (user_id, start_date)
                           VALUES (%s, %s) ON DUPLICATE KEY
                           UPDATE start_date =
                           VALUES (start_date)
                           """, (user_id, start_date))

            # 对最近一条尚未对账的预测进行回填；没有待对账记录时不插入残缺记录。
            cursor.execute("""
                SELECT pred_id, predicted_date
                FROM prediction_logs
                WHERE user_id = %s AND actual_date IS NULL
                ORDER BY ABS(DATEDIFF(predicted_date, %s)), created_at ASC
                LIMIT 1
                FOR UPDATE
            """, (user_id, start_date))
            pending = cursor.fetchone()
            if pending:
                error_days = (start_date - pending["predicted_date"]).days
                cursor.execute("""
                    UPDATE prediction_logs
                    SET actual_date = %s, error_days = %s
                    WHERE pred_id = %s AND user_id = %s
                """, (start_date, error_days, pending["pred_id"], user_id))

        connection.commit()
        return {"status": "success", "message": "周期开始记录成功"}
    except HTTPException:
        connection.rollback()
        raise
    except pymysql.err.IntegrityError:
        connection.rollback()
        raise HTTPException(status_code=409, detail="该日期已经存在周期记录")
    except Exception:
        connection.rollback()
        logger.exception("log_start failed for user_id=%s", user_id)
        raise HTTPException(status_code=500, detail="服务器处理周期记录失败")
    finally:
        connection.close()


@router.post("/log_end")
def log_end(req: LogEndRequest, user_id: int = Depends(get_current_user_id)):
    """标记经期结束（或调整区间结束日）。

    匹配策略：
    1. 优先匹配最新且未结束（end_date IS NULL）的周期；
    2. 若都已闭合，则匹配最新周期，用本次 end_date 修正/覆盖其结束日。
    这样自动闭合给出的默认区间，用户可以随时用"标记结束"调整。
    """
    connection = None
    end_date_obj = req.end_date
    if end_date_obj > date.today():
        raise HTTPException(status_code=400, detail="结束日期不能晚于今天")

    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            # 0. 若指定了 cycle_id，精确定位该周期（用于修正历史周期）
            if req.cycle_id is not None:
                cursor.execute("""
                    SELECT cycle_id, start_date FROM cycles
                    WHERE cycle_id = %s AND user_id = %s
                """, (req.cycle_id, user_id))
                active_cycle = cursor.fetchone()
                if not active_cycle:
                    raise HTTPException(status_code=404, detail="未找到该周期记录")
            else:
                # 1. 优先：最新未结束周期
                cursor.execute("""
                    SELECT cycle_id, start_date FROM cycles
                    WHERE user_id = %s AND end_date IS NULL
                    ORDER BY start_date DESC LIMIT 1
                """, (user_id,))
                active_cycle = cursor.fetchone()

                # 2. 回退：最新周期（允许修正已自动闭合的结束日）
                if not active_cycle:
                    cursor.execute("""
                        SELECT cycle_id, start_date FROM cycles
                        WHERE user_id = %s
                        ORDER BY start_date DESC LIMIT 1
                    """, (user_id,))
                    active_cycle = cursor.fetchone()

            if not active_cycle:
                raise HTTPException(status_code=400, detail="未找到对应的经期开始记录，请先标记开始。")

            start_date = active_cycle['start_date']
            start_date_obj = _normalize_date(start_date)

            if end_date_obj < start_date_obj:
                raise HTTPException(status_code=400, detail="结束日期不能早于开始日期")

            # 无论是自动闭合还是指定 cycle_id，都要防止与前后周期重叠
            cursor.execute("""
                SELECT cycle_id, start_date, end_date FROM cycles
                WHERE user_id = %s AND cycle_id <> %s AND start_date < %s
                ORDER BY start_date DESC LIMIT 1
            """, (user_id, active_cycle['cycle_id'], start_date_obj))
            prev_cycle = cursor.fetchone()
            if prev_cycle:
                prev_end = _normalize_date(prev_cycle['end_date'])
                if prev_end is None:
                    raise HTTPException(status_code=400, detail="前一周期尚未结束，请先处理前一条记录")
                if prev_end >= start_date_obj:
                    raise HTTPException(status_code=400, detail="与前一周期重叠，请重新选择结束日期")

            cursor.execute("""
                SELECT cycle_id, start_date FROM cycles
                WHERE user_id = %s AND cycle_id <> %s AND start_date > %s
                ORDER BY start_date ASC LIMIT 1
            """, (user_id, active_cycle['cycle_id'], start_date_obj))
            next_cycle = cursor.fetchone()
            if next_cycle:
                next_start_obj = _normalize_date(next_cycle['start_date'])
                if end_date_obj >= next_start_obj:
                    raise HTTPException(status_code=400, detail="与后续周期重叠，请重新选择结束日期")

            bleeding_days = (end_date_obj - start_date_obj).days + 1

            cursor.execute("""
                UPDATE cycles SET end_date = %s, bleeding_days = %s WHERE cycle_id = %s
            """, (end_date_obj, bleeding_days, active_cycle['cycle_id']))

            # 3. 重算所有周期的 cycle_length（周期长度 = 下一周期开始 - 本周期开始）
            recalculate_cycle_lengths(cursor, user_id)

        connection.commit()
        return {"status": "success", "message": "🏁 成功标记经期结束！数据已更新。"}
    except HTTPException as he:
        raise he
    except Exception:
        if connection is not None:
            connection.rollback()
        logger.exception("log_end failed for user_id=%s", user_id)
        raise HTTPException(status_code=500, detail="记录经期结束失败，请稍后重试")
    finally:
        if connection is not None:
            connection.close()


@router.put("/cycles/{cycle_id}")
def update_cycle(cycle_id: int, req: CycleUpdateRequest, user_id: int = Depends(get_current_user_id)):
    """编辑一个已存在的周期（修正开始/结束日期）。"""
    connection = None
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cycle = get_cycle_by_id(cursor, user_id, cycle_id)
            if not cycle:
                raise HTTPException(status_code=404, detail="周期不存在")

            # 使用 model_fields_set 区分“未传字段”和“显式传 null”。
            # 这样 end_date=null 才能按公开契约取消周期闭合。
            if "start_date" in req.model_fields_set:
                new_start = req.start_date
            else:
                new_start = cycle['start_date']
            if new_start is None:
                raise HTTPException(status_code=422, detail="开始日期不能为空")

            if new_start > date.today():
                raise HTTPException(status_code=400, detail="开始日期不能晚于今天")

            if "end_date" in req.model_fields_set:
                new_end = req.end_date  # null 表示取消闭合
            else:
                new_end = cycle['end_date']

            if new_end is not None and new_end > date.today():
                raise HTTPException(status_code=400, detail="结束日期不能晚于今天")

            # 校验：结束不能早于开始
            if new_end is not None and new_end < new_start:
                raise HTTPException(status_code=400, detail="结束日期不能早于开始日期")

            # 校验：最近前驱周期
            cursor.execute("""
                SELECT cycle_id, start_date, end_date FROM cycles
                WHERE user_id = %s AND cycle_id <> %s AND start_date < %s
                ORDER BY start_date DESC LIMIT 1
            """, (user_id, cycle_id, new_start))
            prev_cycle = cursor.fetchone()
            if prev_cycle:
                prev_end = prev_cycle['end_date']
                if prev_end is None:
                    # 前驱是未闭合周期，不允许在其后新增/移动周期
                    raise HTTPException(status_code=400, detail="不能在前一未闭合周期之后创建或移动周期")
                prev_end_obj = _normalize_date(prev_end)
                if prev_end_obj >= new_start:
                    raise HTTPException(status_code=400, detail="与已有周期重叠：开始日期不晚于前一周期结束日")

            # 校验：最近后继周期
            cursor.execute("""
                SELECT cycle_id, start_date FROM cycles
                WHERE user_id = %s AND cycle_id <> %s AND start_date > %s
                ORDER BY start_date ASC LIMIT 1
            """, (user_id, cycle_id, new_start))
            next_cycle = cursor.fetchone()
            if next_cycle:
                next_start = next_cycle['start_date']
                next_start_obj = _normalize_date(next_start)
                if new_end is None:
                    raise HTTPException(status_code=400, detail="不能把存在后续周期的记录设为未结束周期")
                if new_end >= next_start_obj:
                    raise HTTPException(status_code=400, detail="与已有周期重叠：结束日期不早于下一周期开始日")

            # 更新周期
            if new_end is not None:
                bleeding_days = (new_end - new_start).days + 1
            else:
                bleeding_days = None
            update_cycle_dates(cursor, cycle_id, new_start, new_end, bleeding_days)

            # 重算所有周期的 cycle_length
            recalculate_cycle_lengths(cursor, user_id)

        connection.commit()
        return {"status": "success", "message": "✅ 周期已更新！"}
    except HTTPException as he:
        raise he
    except Exception:
        if connection is not None:
            connection.rollback()
        logger.exception("update_cycle failed for user_id=%s cycle_id=%s", user_id, cycle_id)
        raise HTTPException(status_code=500, detail="更新周期失败，请稍后重试")
    finally:
        if connection is not None:
            connection.close()


@router.delete("/cycles/{cycle_id}")
def delete_cycle_endpoint(cycle_id: int, user_id: int = Depends(get_current_user_id)):
    """删除一个误操作的周期。"""
    connection = None
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cycle = get_cycle_by_id(cursor, user_id, cycle_id)
            if not cycle:
                raise HTTPException(status_code=404, detail="周期不存在")

            delete_cycle(cursor, cycle_id)

            # 重算剩余周期的 cycle_length
            recalculate_cycle_lengths(cursor, user_id)

        connection.commit()
        return {"status": "success", "message": "🗑️ 周期已删除！"}
    except HTTPException as he:
        raise he
    except Exception:
        if connection is not None:
            connection.rollback()
        logger.exception("delete_cycle failed for user_id=%s cycle_id=%s", user_id, cycle_id)
        raise HTTPException(status_code=500, detail="删除周期失败，请稍后重试")
    finally:
        if connection is not None:
            connection.close()


@router.get("/prediction", response_model=PredictionResponse)
def get_user_prediction(user_id: int = Depends(get_current_user_id)):
    try:
        # 提取用户最新的 9 维滑动窗口特征
        features_dict, last_start_date = get_latest_features_for_user(user_id)
    except ValueError as ve:
        return {"status": "insufficient_data", "message": str(ve), "prediction": None}
    except Exception:
        logger.exception("Feature extraction failed for user_id=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="特征提取失败，请稍后重试",
        )

    prediction_result = _prediction_service.predict(features_dict, last_start_date)
    if prediction_result is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="预测引擎内部计算错误",
        )

    # 记录待对账预测，实际周期开始时由 /log_start 回填 actual_date/error_days。
    connection = None
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT pred_id FROM prediction_logs
                WHERE user_id = %s AND predicted_date = %s AND actual_date IS NULL
                LIMIT 1
            """, (user_id, prediction_result["next_period_start"]))
            if cursor.fetchone() is None:
                cursor.execute("""
                    INSERT INTO prediction_logs (user_id, predicted_date)
                    VALUES (%s, %s)
                """, (user_id, prediction_result["next_period_start"]))
        connection.commit()
    except Exception:
        if connection is not None:
            connection.rollback()
        logger.exception("prediction log write failed for user_id=%s", user_id)
    finally:
        if connection is not None:
            connection.close()

    return {"status": "success", "prediction": prediction_result}


class DailyLogRequest(BaseModel):
    log_date: date
    mood_level: int = Field(default=0, ge=0, le=3)
    cramps_severity: int = Field(default=0, ge=0, le=3)
    is_exercise: bool = False
    is_intercourse: bool = False
    exercise_type: str | None = Field(default=None, max_length=50)
    exercise_minutes: int = Field(default=0, ge=0, le=1440)
    diet_tag: str | None = Field(default=None, max_length=100)
    journal_text: str | None = Field(default=None, max_length=4000)


@router.post("/daily_log")
def save_daily_log(req: DailyLogRequest, user_id: int = Depends(get_current_user_id)):
    """保存每日健康日志，并基于症状与日记由 AI 生成个性化健康与膳食营养建议"""
    connection = None
    if req.log_date > date.today():
        raise HTTPException(status_code=400, detail="日志日期不能晚于今天")

    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO daily_logs
                (user_id, log_date, mood_level, cramps_severity, is_exercise, is_intercourse,
                 exercise_type, exercise_minutes, diet_tag, journal_text)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    mood_level = VALUES(mood_level),
                    cramps_severity = VALUES(cramps_severity),
                    is_exercise = VALUES(is_exercise),
                    is_intercourse = VALUES(is_intercourse),
                    exercise_type = VALUES(exercise_type),
                    exercise_minutes = VALUES(exercise_minutes),
                    diet_tag = VALUES(diet_tag),
                    journal_text = VALUES(journal_text)
            """, (
                user_id, req.log_date, req.mood_level, req.cramps_severity,
                req.is_exercise, req.is_intercourse, req.exercise_type,
                req.exercise_minutes, req.diet_tag, req.journal_text
            ))
        connection.commit()

        # AI 智能健康与膳食营养建议
        advices = []
        if req.cramps_severity >= 2:
            advices.append("检测到腹痛较为明显，建议多喝温开水，适当补充富含镁元素与维生素 B6 的食物（如香蕉、坚果、深色蔬菜）以缓解肌肉痉挛。")
        if req.is_exercise and req.exercise_minutes > 45:
            advices.append(f"今日进行了 {req.exercise_minutes} 分钟的 {req.exercise_type or '运动'}，体力消耗较大，请注意及时补充电解质和优质蛋白质。")
        if req.diet_tag and ("辛辣" in req.diet_tag or "油腻" in req.diet_tag):
            advices.append("饮食偏向重口味，可能会加重盆腔充血或身体负担，建议多吃富含膳食纤维的果蔬促进代谢。")
        if req.journal_text and any(k in req.journal_text for k in ["压力", "焦虑", "失眠", "累", "烦"]):
            advices.append("日记中透露出一定的生活压力，建议睡前进行 10 分钟深呼吸放松或泡个温水脚，保证充足睡眠。")
        if not advices:
            advices.append("今日身体状态平稳，继续保持规律作息和均衡饮食哦！")

        return {
            "status": "success",
            "message": "✨ 健康日志保存成功！",
            "ai_health_advice": advices
        }
    except Exception:
        if connection is not None:
            connection.rollback()
        logger.exception("save_daily_log failed for user_id=%s", user_id)
        raise HTTPException(status_code=500, detail="保存健康日志失败，请稍后重试")
    finally:
        if connection is not None:
            connection.close()
