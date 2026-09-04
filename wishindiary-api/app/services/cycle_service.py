"""Cycle business logic（周期业务 service 层）。

将周期写入、闭合、编辑、删除的业务规则从 router 下沉到本层，
统一通过 `with transaction()` 管理事务，可预期的失败抛 AppError，
由全局异常处理器统一收敛为 {"error": {...}} 响应格式。
"""

import logging
from datetime import date, datetime

import pymysql

from app.core.audit import audit
from app.core.database import transaction
from app.core.errors import AppError
from app.repositories import (
    get_cycle_by_id,
    close_cycle,
    delete_cycle,
    get_cycle_for_log_end,
    get_next_cycle,
    get_prev_cycle,
    get_unclosed_cycle_for_update,
    get_conflicting_closed_cycle,
    insert_cycle,
    recalculate_cycle_lengths,
    update_cycle_dates,
    update_cycle_end,
)
from app.repositories.prediction_log_repository import (
    get_pending_prediction_for_reconcile,
    reconcile_prediction,
)

logger = logging.getLogger(__name__)

_DEFAULT_BLEEDING_DAYS = 5

# 哨兵值：区分"未传字段"与"显式传 None"
_UNSET = object()


def _normalize_date(value):
    """兼容数据库返回的 date / datetime / str。"""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return datetime.strptime(value, "%Y-%m-%d").date()
    return value


class CycleService:
    """周期生命周期业务：开始 / 结束 / 编辑 / 删除。"""

    def log_start(self, user_id: int, start_date: date) -> dict:
        """标记周期开始，并自动闭合上一未结束周期、回填预测对账。"""
        if start_date > date.today():
            raise AppError(400, "invalid_input", "开始日期不能晚于今天")

        try:
            with transaction() as connection:
                with connection.cursor() as cursor:
                    # 0. 行级排他锁，防止并发读写
                    unclosed_cycle = get_unclosed_cycle_for_update(cursor, user_id)

                    # 1. 若存在进行中的周期，新开始日期不能早于/等于其开始日
                    if unclosed_cycle:
                        prev_start = _normalize_date(unclosed_cycle["start_date"])
                        if start_date <= prev_start:
                            raise AppError(
                                400,
                                "conflict",
                                "存在进行中的周期：新周期开始日期不能早于或等于上个未结束周期",
                            )

                    # 2. 与已闭合周期的区间重叠校验（在闭合未闭合周期之前执行，
                    #    避免 close_cycle 把其 end_date 写成 start_date 后自相命中）。
                    conflicting = get_conflicting_closed_cycle(cursor, user_id, start_date)
                    if conflicting:
                        raise AppError(
                            400,
                            "conflict",
                            "与已有经期记录重叠：该日期已落在一条已结束的经期记录区间内",
                        )

                    if unclosed_cycle:
                        cycle_length = (start_date - prev_start).days
                        # 闭合上一周期
                        close_cycle(
                            cursor,
                            unclosed_cycle["cycle_id"],
                            start_date,
                            cycle_length,
                            _DEFAULT_BLEEDING_DAYS,
                        )

                    # 3. 写入新周期 (利用 UNIQUE KEY uk_user_start 兜底幂等性)
                    insert_cycle(cursor, user_id, start_date)

                    # 4. 对最近一条尚未对账的预测进行回填；没有待对账记录时不插入残缺记录。
                    pending = get_pending_prediction_for_reconcile(cursor, user_id, start_date)
                    if pending:
                        error_days = (start_date - pending["predicted_date"]).days
                        reconcile_prediction(
                            cursor,
                            pending["pred_id"],
                            user_id,
                            start_date,
                            error_days,
                        )

            audit("cycle.log_start", actor_user_id=user_id, success=True, details={"start_date": start_date.isoformat()})
            return {"status": "success", "message": "周期开始记录成功"}
        except pymysql.err.IntegrityError:
            raise AppError(409, "conflict", "该日期已经存在周期记录")
        except AppError:
            raise
        except Exception:
            logger.exception("log_start failed for user_id=%s", user_id)
            raise AppError(500, "internal_error", "服务器处理周期记录失败")

    def log_end(self, user_id: int, end_date: date, cycle_id: int | None = None) -> dict:
        """标记经期结束（或调整区间结束日）。

        匹配策略：
        1. 优先匹配最新且未结束（end_date IS NULL）的周期；
        2. 若都已闭合，则匹配最新周期，用本次 end_date 修正/覆盖其结束日。
        """
        if end_date > date.today():
            raise AppError(400, "invalid_input", "结束日期不能晚于今天")

        try:
            with transaction() as connection:
                with connection.cursor() as cursor:
                    active_cycle = get_cycle_for_log_end(cursor, user_id, cycle_id)
                    if not active_cycle:
                        raise AppError(400, "invalid_input", "未找到对应的经期开始记录，请先标记开始。")

                    start_date_obj = _normalize_date(active_cycle["start_date"])
                    if end_date < start_date_obj:
                        raise AppError(400, "invalid_input", "结束日期不能早于开始日期")

                    # 防止与前后周期重叠
                    prev_cycle = get_prev_cycle(
                        cursor, user_id, active_cycle["cycle_id"], start_date_obj
                    )
                    if prev_cycle:
                        prev_end = _normalize_date(prev_cycle["end_date"])
                        if prev_end is None:
                            raise AppError(400, "invalid_input", "前一周期尚未结束，请先处理前一条记录")
                        if prev_end >= start_date_obj:
                            raise AppError(400, "invalid_input", "与前一周期重叠，请重新选择结束日期")

                    next_cycle = get_next_cycle(
                        cursor, user_id, active_cycle["cycle_id"], start_date_obj
                    )
                    if next_cycle:
                        next_start_obj = _normalize_date(next_cycle["start_date"])
                        if end_date >= next_start_obj:
                            raise AppError(400, "invalid_input", "与后续周期重叠，请重新选择结束日期")

                    bleeding_days = (end_date - start_date_obj).days + 1
                    update_cycle_end(cursor, active_cycle["cycle_id"], end_date, bleeding_days)

                    # 重算所有周期的 cycle_length（周期长度 = 下一周期开始 - 本周期开始）
                    recalculate_cycle_lengths(cursor, user_id)

            audit("cycle.log_end", actor_user_id=user_id, success=True, details={"end_date": end_date.isoformat(), "cycle_id": active_cycle["cycle_id"]})
            return {"status": "success", "message": "🏁 成功标记经期结束！数据已更新。"}
        except AppError:
            raise
        except Exception:
            logger.exception("log_end failed for user_id=%s", user_id)
            raise AppError(500, "internal_error", "记录经期结束失败，请稍后重试")

    def update_cycle(
        self,
        user_id: int,
        cycle_id: int,
        start_date=_UNSET,
        end_date=_UNSET,
    ) -> dict:
        """编辑一个已存在的周期（修正开始/结束日期）。

        用 _UNSET 区分"未传字段"和"显式传 None"：
        end_date=_UNSET 表示保留原值；end_date=None 表示取消闭合。
        """
        try:
            with transaction() as connection:
                with connection.cursor() as cursor:
                    cycle = get_cycle_by_id(cursor, user_id, cycle_id)
                    if not cycle:
                        raise AppError(404, "not_found", "周期不存在")

                    new_start = start_date if start_date is not _UNSET else cycle["start_date"]
                    if new_start is None:
                        raise AppError(422, "validation_error", "开始日期不能为空")
                    if new_start > date.today():
                        raise AppError(400, "invalid_input", "开始日期不能晚于今天")

                    new_end = end_date if end_date is not _UNSET else cycle["end_date"]
                    if new_end is not None and new_end > date.today():
                        raise AppError(400, "invalid_input", "结束日期不能晚于今天")
                    if new_end is not None and new_end < new_start:
                        raise AppError(400, "invalid_input", "结束日期不能早于开始日期")

                    # 校验：最近前驱周期
                    prev_cycle = get_prev_cycle(cursor, user_id, cycle_id, new_start)
                    if prev_cycle:
                        prev_end = prev_cycle["end_date"]
                        if prev_end is None:
                            raise AppError(400, "invalid_input", "不能在前一未闭合周期之后创建或移动周期")
                        prev_end_obj = _normalize_date(prev_end)
                        if prev_end_obj >= new_start:
                            raise AppError(400, "invalid_input", "与已有周期重叠：开始日期不晚于前一周期结束日")

                    # 校验：最近后继周期
                    next_cycle = get_next_cycle(cursor, user_id, cycle_id, new_start)
                    if next_cycle:
                        next_start_obj = _normalize_date(next_cycle["start_date"])
                        if new_end is None:
                            raise AppError(400, "invalid_input", "不能把存在后续周期的记录设为未结束周期")
                        if new_end >= next_start_obj:
                            raise AppError(400, "invalid_input", "与已有周期重叠：结束日期不早于下一周期开始日")

                    # 更新周期
                    if new_end is not None:
                        bleeding_days = (new_end - new_start).days + 1
                    else:
                        bleeding_days = None
                    update_cycle_dates(cursor, cycle_id, new_start, new_end, bleeding_days)
                    recalculate_cycle_lengths(cursor, user_id)

            audit("cycle.update", actor_user_id=user_id, success=True, details={"cycle_id": cycle_id, "start_date": new_start.isoformat(), "end_date": new_end.isoformat() if new_end else None})
            return {"status": "success", "message": "✅ 周期已更新！"}
        except AppError:
            raise
        except Exception:
            logger.exception("update_cycle failed for user_id=%s cycle_id=%s", user_id, cycle_id)
            raise AppError(500, "internal_error", "更新周期失败，请稍后重试")

    def delete_cycle(self, user_id: int, cycle_id: int) -> dict:
        """删除一个误操作的周期，并重算剩余周期的周期长度。"""
        try:
            with transaction() as connection:
                with connection.cursor() as cursor:
                    cycle = get_cycle_by_id(cursor, user_id, cycle_id)
                    if not cycle:
                        raise AppError(404, "not_found", "周期不存在")

                    delete_cycle(cursor, cycle_id)
                    recalculate_cycle_lengths(cursor, user_id)

            return {"status": "success", "message": "🗑️ 周期已删除！"}
        except AppError:
            raise
        except Exception:
            logger.exception("delete_cycle failed for user_id=%s cycle_id=%s", user_id, cycle_id)
            raise AppError(500, "internal_error", "删除周期失败，请稍后重试")
