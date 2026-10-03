from datetime import timezone

from app.core.calendar_time import utc_now, user_today
from app.core.database import transaction
from app.core.errors import AppError
from app.repositories.cycle_repository import get_cycle_by_id, get_user_latest_cycle


class TrackingService:
    def confirm(self, user_id, cycle_id, req):
        with transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT user_id FROM users WHERE user_id=%s FOR UPDATE", (user_id,))
                today = user_today(cursor, user_id)
                cycle = get_cycle_by_id(cursor, user_id, cycle_id)
                if cycle is None:
                    raise AppError(404, "not_found", "周期不存在")
                if not cycle["start_date"] <= req.as_of_date <= today:
                    raise AppError(400, "invalid_input", "确认日期须在开始日和账户今天之间")
                if req.kind == "no_onset":
                    latest = get_user_latest_cycle(cursor, user_id)
                    if latest["start_date"] != cycle["start_date"]:
                        raise AppError(400, "conflict", "已记录后续开始，不能确认该次仍未开始")
                elif req.kind != "unknown" and cycle["cycle_length"] is None:
                    raise AppError(400, "invalid_input", "请在已有后续开始日的间隔上核对是否漏记")
                cursor.execute("SELECT notification_timezone FROM users WHERE user_id=%s", (user_id,))
                tz = cursor.fetchone()["notification_timezone"]
                cursor.execute("INSERT INTO cycle_tracking_events (cycle_id,user_id,anchor_start_date,kind,as_of_date,known_at,timezone_name) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (cycle_id, user_id, cycle["start_date"], req.kind, req.as_of_date,
                     utc_now().astimezone(timezone.utc).replace(tzinfo=None), tz))
        return {"status": "success", "message": "核对信息已保存；不会自动补造日期或改变线上预测。"}
