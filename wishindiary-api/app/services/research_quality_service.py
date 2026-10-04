"""Authorized cohort quality, distinct from platform operational counters."""
import json
from datetime import timedelta
from zoneinfo import ZoneInfo

from app.core.calendar_time import utc_now
from app.core.research_policy import POLICY_VERSION
from app.features.lifestyle_features import utc_instant
from app.features.research_background import background_group


def research_quality(cursor):
    cursor.execute("SELECT e.user_id,e.known_at,u.notification_timezone,b.payload FROM research_consent_events e "
                   "JOIN (SELECT user_id,MAX(event_id) latest FROM research_consent_events GROUP BY user_id) s ON e.event_id=s.latest "
                   "JOIN users u ON u.user_id=e.user_id LEFT JOIN research_background_revisions b ON b.revision_id="
                   "(SELECT MAX(revision_id) FROM research_background_revisions WHERE user_id=e.user_id) "
                   "WHERE e.action='grant' AND e.policy_version=%s ORDER BY e.user_id", (POLICY_VERSION,))
    participants = list(cursor.fetchall())
    result = {'available': True, 'participants': len(participants), 'daily_records': 0,
              'timely_records': 0, 'backfilled_records': 0, 'unknown_recording_time': 0,
              'calendar_days': 0, 'observed_days': 0, 'sleep_days': 0, 'stress_days': 0, 'exercise_days': 0,
              'background_groups': dict.fromkeys(('unknown', 'explicit_none', 'reported_context'), 0)}
    if not participants:
        result['coverage_pct'] = None
        return result
    identifiers = [row['user_id'] for row in participants]
    placeholders = ','.join(['%s'] * len(identifiers))
    cursor.execute(f'SELECT d.user_id,d.log_date,f.known_at,f.source,f.timezone_name,r.payload FROM daily_logs d '
                   'JOIN daily_log_revisions f ON f.revision_id=(SELECT MIN(revision_id) FROM daily_log_revisions WHERE log_id=d.log_id) '
                   'JOIN daily_log_revisions r ON r.revision_id=(SELECT MAX(revision_id) FROM daily_log_revisions WHERE log_id=d.log_id) '
                   f'WHERE d.user_id IN ({placeholders}) ORDER BY d.user_id,d.log_date LIMIT 100001', identifiers)
    rows = list(cursor.fetchall())
    if len(rows) > 100_000:
        return {'available': False, 'participants': len(participants), 'message': '授权队列超过在线汇总上限，请使用有界离线统计'}
    by_user = {row['user_id']: row for row in participants}
    windows = {}
    now = utc_now()
    for participant in participants:
        tz = ZoneInfo(participant['notification_timezone'])
        end = now.astimezone(tz).date()
        start = max(end - timedelta(days=28), utc_instant(participant['known_at']).astimezone(tz).date())
        windows[participant['user_id']] = (start, end)
        result['calendar_days'] += max(0, (end - start).days)
        payload = participant['payload']
        fields = json.loads(payload) if isinstance(payload, str) else payload or {}
        group = background_group(fields)
        # Underage background automatically withdraws; defensive handling if
        # old/manual data violates that invariant.
        if group in result['background_groups']:
            result['background_groups'][group] += 1
    result['daily_records'] = len(rows)
    for row in rows:
        if row['source'] != 'user_recorded':
            result['unknown_recording_time'] += 1
        else:
            delay = (utc_instant(row['known_at']).astimezone(ZoneInfo(row['timezone_name'])).date() - row['log_date']).days
            result['timely_records' if 0 <= delay <= 1 else 'backfilled_records' if delay > 1 else 'unknown_recording_time'] += 1
        start, end = windows[row['user_id']]
        if not start <= row['log_date'] < end or utc_instant(row['known_at']) < utc_instant(by_user[row['user_id']]['known_at']):
            continue
        payload = json.loads(row['payload']) if isinstance(row['payload'], str) else row['payload']
        if row['source'] != 'user_recorded':
            continue
        result['observed_days'] += 1
        result['sleep_days'] += payload.get('sleep_duration_minutes') is not None
        result['stress_days'] += payload.get('stress_level') is not None
        result['exercise_days'] += payload.get('is_exercise') is False or payload.get('exercise_minutes') is not None
    result['coverage_pct'] = round(100 * result['observed_days'] / result['calendar_days'], 2) if result['calendar_days'] else None
    return result
