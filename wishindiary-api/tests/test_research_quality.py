from datetime import datetime, timezone

from app.core.database import transaction
from app.core.research_policy import POLICY_VERSION


def test_authorized_quality_preserves_unknown_and_counts_empty_calendar_days(client, auth_header, monkeypatch):
    from app.repositories import daily_log_repository
    from app.services import research_participation_service, research_quality_service

    user_id = client.get('/api/v1/auth/session').json()['user_id']
    now = datetime(2024, 1, 31, tzinfo=timezone.utc)
    monkeypatch.setattr(research_quality_service, 'utc_now', lambda: now)
    monkeypatch.setattr(daily_log_repository, 'utc_now', lambda: now.replace(day=30))
    monkeypatch.setattr(research_participation_service, 'utc_now', lambda: now.replace(day=1))
    for day, payload in [(29, {'sleep_duration_minutes': 480, 'stress_level': 0, 'is_exercise': False}),
                         (10, {'stress_level': 2}), (20, {})]:
        assert client.post('/api/v1/daily_log', json={'log_date': f'2024-01-{day:02}', **payload}).status_code == 200
    with transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE daily_log_revisions SET source='legacy_unknown' WHERE user_id=%s AND log_date='2024-01-20'", (user_id,))
    with transaction() as connection:
        with connection.cursor() as cursor:
            quality = research_quality_service.research_quality(cursor)
    assert quality['participants'] == 0 and quality['daily_records'] == 0 and quality['coverage_pct'] is None
    assert client.put('/api/v1/research/participation', json={'participate': True,
        'policy_version': POLICY_VERSION, 'adult_confirmed': True}).status_code == 200
    with transaction() as connection:
        with connection.cursor() as cursor:
            quality = research_quality_service.research_quality(cursor)
    assert quality['daily_records'] == 3
    assert quality['timely_records'] == quality['backfilled_records'] == quality['unknown_recording_time'] == 1
    assert quality['calendar_days'] == 28 and quality['observed_days'] == 2
    assert quality['sleep_days'] == quality['exercise_days'] == 1 and quality['stress_days'] == 2
    assert quality['background_groups'] == {'unknown': 1, 'explicit_none': 0, 'reported_context': 0}
    assert 'user_id' not in quality
    assert client.put('/api/v1/research/participation', json={'participate': False}).status_code == 200
    with transaction() as connection:
        with connection.cursor() as cursor:
            assert research_quality_service.research_quality(cursor)['participants'] == 0


def test_same_day_join_has_no_completed_calendar_denominator(client, auth_header, monkeypatch):
    from app.core.config import settings
    user_id = client.get('/api/v1/auth/session').json()['user_id']
    monkeypatch.setattr(settings, 'ADMIN_USER_IDS', str(user_id))
    assert client.put('/api/v1/research/participation', json={'participate': True,
        'policy_version': POLICY_VERSION, 'adult_confirmed': True}).status_code == 200
    result = client.get('/api/v1/admin/research').json()
    assert result['data']['users'] == result['research_quality']['participants'] == 1
    assert result['research_quality']['calendar_days'] == 0 and result['research_quality']['coverage_pct'] is None
