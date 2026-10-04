"""Private, bounded snapshots with current in-app consent; never personal exports."""
import hashlib
import hmac
import json

from app.core.config import settings
from app.core.database import transaction
from app.core.research_policy import BACKGROUND_FIELDS, POLICY_VERSION
from app.repositories.daily_log_repository import RESEARCH_FIELDS
from app.repositories.research_participation_repository import active_participants, authorization_digest

ROW_LIMIT = 1_000_000


def fingerprint(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str, separators=(',', ':')).encode()).hexdigest()


def snapshot_signature(data_sha256, consent_sha256):
    message = f'research-snapshot-v1/{POLICY_VERSION}/{data_sha256}/{consent_sha256}'.encode()
    return hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()


def read_authorized_database():
    result = {}
    with transaction() as connection:
        with connection.cursor() as cursor:
            # Enrollment, edits and deletion all take the same user lock. Hold
            # it only while copying the bounded event snapshot, never during ML.
            cursor.execute('SELECT user_id FROM users ORDER BY user_id LIMIT 10001 FOR UPDATE')
            if len(cursor.fetchall()) > 10_000:
                raise ValueError('Too many accounts for this bounded research export')
            participants = active_participants(cursor)
            identifiers = [row['user_id'] for row in participants]
            result['enrollment'] = {row['user_id']: row['known_at'] for row in participants}
            for table in ('cycle_revisions', 'daily_log_revisions', 'cycle_tracking_events', 'research_background_revisions'):
                if not identifiers:
                    result[table] = []
                    continue
                placeholders = ','.join(['%s'] * len(identifiers))
                cursor.execute(f'SELECT * FROM {table} WHERE user_id IN ({placeholders}) ORDER BY user_id LIMIT {ROW_LIMIT + 1}', identifiers)
                rows = list(cursor.fetchall())
                if len(rows) > ROW_LIMIT:
                    raise ValueError('Dataset too large for this bounded research export')
                if table in ('daily_log_revisions', 'research_background_revisions'):
                    fields = RESEARCH_FIELDS if table == 'daily_log_revisions' else BACKGROUND_FIELDS
                    for row in rows:
                        payload = json.loads(row['payload']) if isinstance(row['payload'], str) else row['payload']
                        row['payload'] = {key: payload.get(key) for key in fields}
                result[table] = rows
            if identifiers:
                cursor.execute(f'SELECT user_id,cycle_history_reset_at FROM users WHERE user_id IN ({placeholders})', identifiers)
                result['resets'] = {row['user_id']: row['cycle_history_reset_at'] for row in cursor.fetchall() if row['cycle_history_reset_at']}
            else:
                result['resets'] = {}
            digest = authorization_digest(participants)
    return {'schema_version': 1, 'policy_version': POLICY_VERSION, 'data': result,
            'authorization_sha256': digest, 'dataset_sha256': fingerprint(result),
            'signature': snapshot_signature(fingerprint(result), digest)}


def authorization_is_current(proof):
    if not isinstance(proof, dict) or proof.get('policy_version') != POLICY_VERSION:
        return False
    with transaction() as connection:
        with connection.cursor() as cursor:
            current = authorization_digest(active_participants(cursor))
    return (hmac.compare_digest(str(proof.get('authorization_sha256', '')), current)
            and hmac.compare_digest(str(proof.get('signature', '')),
                                    snapshot_signature(proof.get('dataset_sha256', ''), current)))


def validate_snapshot(snapshot):
    if snapshot.get('schema_version') != 1 or not isinstance(snapshot.get('data'), dict):
        raise ValueError('Only a signed research snapshot is accepted; personal exports are not research authorization')
    if fingerprint(snapshot['data']) != snapshot.get('dataset_sha256'):
        raise ValueError('Research snapshot content has changed')
    if not authorization_is_current(snapshot):
        raise ValueError('Research consent changed or snapshot signature is invalid; create a new snapshot')
    return snapshot['data']


def report_authorization(snapshot):
    return {key: snapshot[key] for key in ('policy_version', 'authorization_sha256', 'dataset_sha256', 'signature')}
