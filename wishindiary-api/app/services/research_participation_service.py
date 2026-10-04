import json
from datetime import timezone
from uuid import uuid4

from app.core.calendar_time import utc_now
from app.core.database import transaction
from app.core.errors import AppError
from app.core.research_policy import POLICY, POLICY_VERSION
from app.repositories.research_participation_repository import current_background, latest_consent


class ResearchParticipationService:
    def get(self, user_id):
        with transaction() as connection:
            with connection.cursor() as cursor:
                event = latest_consent(cursor, user_id)
                background = current_background(cursor, user_id)
        active = bool(event and event["action"] == "grant" and event["policy_version"] == POLICY_VERSION)
        return {"status": "success", "policy": POLICY, "participating": active,
                "decision_at": event["known_at"].replace(tzinfo=timezone.utc).isoformat() if event else None,
                "background": background}

    def decide(self, user_id, req):
        with transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT user_id FROM users WHERE user_id=%s FOR UPDATE", (user_id,))
                if not cursor.fetchone():
                    raise AppError(404, "not_found", "账号不存在")
                current = latest_consent(cursor, user_id)
                if req.participate:
                    if req.policy_version != POLICY_VERSION:
                        raise AppError(409, "conflict", "请阅读并确认当前版本的研究说明")
                    if not req.adult_confirmed or current_background(cursor, user_id)["fields"]["age_band"] == "under18":
                        raise AppError(400, "bad_request", "本阶段研究需要确认已满 18 岁")
                    if current and current["action"] == "grant" and current["policy_version"] == POLICY_VERSION:
                        return {"status": "success", "message": "已参加当前研究，无需重复授权"}
                    action, episode = "grant", uuid4().hex
                else:
                    if not current or current["action"] == "withdraw":
                        return {"status": "success", "message": "当前未参加研究"}
                    action, episode = "withdraw", current["episode_id"]
                cursor.execute("INSERT INTO research_consent_events (user_id,action,policy_version,episode_id,known_at) "
                               "VALUES (%s,%s,%s,%s,%s)", (user_id, action, POLICY_VERSION, episode,
                               utc_now().astimezone(timezone.utc).replace(tzinfo=None)))
        return {"status": "success", "message": "已自愿参加研究" if req.participate else "已撤回研究授权，个人记录和提醒功能继续保留"}

    def save_background(self, user_id, req):
        fields = req.model_dump()
        with transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT notification_timezone FROM users WHERE user_id=%s FOR UPDATE", (user_id,))
                user = cursor.fetchone()
                if not user:
                    raise AppError(404, "not_found", "账号不存在")
                if current_background(cursor, user_id)["fields"] != fields:
                    cursor.execute("INSERT INTO research_background_revisions (user_id,known_at,timezone_name,payload) "
                                   "VALUES (%s,%s,%s,%s)", (user_id, utc_now().astimezone(timezone.utc).replace(tzinfo=None),
                                   user["notification_timezone"], json.dumps(fields)))
        return {"status": "success", "message": "自愿背景已保存；仅用于研究分组，不自动调整预测日期"}

