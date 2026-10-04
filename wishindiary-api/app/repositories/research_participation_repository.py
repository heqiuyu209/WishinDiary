"""Consent decisions and medical context are append-only UTC observations."""
import hashlib
import hmac
import json
from datetime import timezone

from app.core.config import settings
from app.core.research_policy import BACKGROUND_FIELDS, POLICY_VERSION


def latest_consent(cursor, user_id):
    cursor.execute("SELECT action,policy_version,episode_id,known_at,event_id FROM research_consent_events "
                   "WHERE user_id=%s ORDER BY event_id DESC LIMIT 1", (user_id,))
    return cursor.fetchone()


def current_background(cursor, user_id):
    cursor.execute("SELECT payload,known_at FROM research_background_revisions WHERE user_id=%s "
                   "ORDER BY revision_id DESC LIMIT 1", (user_id,))
    row = cursor.fetchone()
    if not row:
        return {"fields": dict.fromkeys(BACKGROUND_FIELDS), "known_at": None}
    payload = json.loads(row["payload"]) if isinstance(row["payload"], str) else row["payload"]
    return {"fields": {key: payload.get(key) for key in BACKGROUND_FIELDS},
            "known_at": row["known_at"].replace(tzinfo=timezone.utc).isoformat()}


def active_participants(cursor):
    cursor.execute("SELECT e.user_id,e.episode_id,e.known_at FROM research_consent_events e "
                   "JOIN (SELECT user_id,MAX(event_id) AS latest FROM research_consent_events GROUP BY user_id) s "
                   "ON e.event_id=s.latest WHERE e.action='grant' AND e.policy_version=%s ORDER BY e.user_id", (POLICY_VERSION,))
    return list(cursor.fetchall())


def authorization_digest(participants):
    records = [(row["user_id"], row["episode_id"], row["known_at"].isoformat()) for row in participants]
    payload = json.dumps([POLICY_VERSION, records], separators=(",", ":")).encode()
    return hmac.new(settings.SECRET_KEY.encode(), payload, hashlib.sha256).hexdigest()

