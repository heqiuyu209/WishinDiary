import copy
import json
from datetime import timedelta

import pytest

from app.core.config import settings
from app.core.research_policy import POLICY_VERSION
from app.features.research_background import background_as_of, background_group
from app.ml.lifestyle_evaluation import build_lifestyle_cases
from app.ml.lifestyle_report import read_lifestyle_report
from app.services.research_dataset_service import read_authorized_database, report_authorization, validate_snapshot
from scripts.lifestyle_backtest import synthetic_event_data


def grant(client):
    assert client.put('/api/v1/research/participation', json={
        'participate': True, 'policy_version': POLICY_VERSION, 'adult_confirmed': True}).status_code == 200


def test_snapshot_excludes_nonparticipants_and_private_fields_and_rechecks_withdrawal(client, auth_header, monkeypatch, tmp_path):
    assert client.post('/api/v1/daily_log', json={'log_date': '2024-01-01', 'stress_level': 2,
        'is_intercourse': True, 'journal_text': 'private journal', 'medication_note': 'private name'}).status_code == 200
    assert not read_authorized_database()['data']['daily_log_revisions']
    grant(client)
    assert client.put('/api/v1/research/background', json={'pregnancy': False}).status_code == 200
    snapshot = read_authorized_database()
    # JSON round-trip reproduces the exact signed data hash.
    snapshot = json.loads(json.dumps(snapshot, default=str))
    data = validate_snapshot(snapshot)
    assert data['daily_log_revisions'] and data['enrollment']
    assert 'private journal' not in json.dumps(data) and 'private name' not in json.dumps(data)
    assert 'is_sex' not in data['daily_log_revisions'][0]['payload']
    tampered = copy.deepcopy(snapshot)
    tampered['data']['daily_log_revisions'][0]['payload']['stress_level'] = 0
    with pytest.raises(ValueError, match='content has changed'):
        validate_snapshot(tampered)
    with pytest.raises(ValueError, match='Only a signed'):
        validate_snapshot(client.get('/api/v1/user/export').json())
    monkeypatch.setattr(settings, 'MODEL_PATH', tmp_path / 'model.skops')
    report = {'schema_version': 1, 'dataset': {'source': 'authorized_database'}, 'authorization': report_authorization(snapshot),
        'evaluation': {'feature_version': 'cycle-lifestyle-research-v1', 'calibration_cutoff': '2022-01-01T00:00:00Z',
                       'test_cutoff': '2023-01-01T00:00:00Z', 'data_as_of': '2024-01-01T00:00:00Z', 'target_coverage_pct': 90}}
    (tmp_path / 'lifestyle_evaluation_report.json').write_text(json.dumps(report))
    assert client.put('/api/v1/research/participation', json={'participate': False}).status_code == 200
    with pytest.raises(ValueError, match='consent changed'):
        validate_snapshot(snapshot)
    assert '授权' in read_lifestyle_report()['message']
    assert not read_authorized_database()['data']['daily_log_revisions']
    grant(client)
    with pytest.raises(ValueError, match='consent changed'):
        validate_snapshot(snapshot)


def test_enrollment_allows_prior_features_but_not_prior_targets_and_background_is_asof():
    data = synthetic_event_data(n_users=1, n_cycles=8)
    before, _ = build_lifestyle_cases(data['cycle_revisions'], data['daily_log_revisions'])
    start = before[1].issued_at
    backgrounds = [{'revision_id': 1, 'user_id': 1, 'known_at': start - timedelta(days=1), 'payload': {'pregnancy': False}},
                   {'revision_id': 2, 'user_id': 1, 'known_at': start + timedelta(days=1), 'payload': {'pregnancy': True}}]
    assert background_group(background_as_of(backgrounds, 1, start)) == 'unknown'
    after, counts = build_lifestyle_cases(data['cycle_revisions'], data['daily_log_revisions'],
        enrollment={1: start}, background_events=backgrounds)
    assert counts['before_enrollment'] > 0
    assert after[0].key == before[1].key and len(after[0].history) >= 3
    assert after[0].background_group == 'unknown' and after[1].background_group == 'reported_context'
    assert background_group({'pregnancy': False}) == 'unknown'
    assert not build_lifestyle_cases(data['cycle_revisions'], data['daily_log_revisions'], enrollment={})[0]


def test_reported_underage_withdraws_in_same_transaction(client, auth_header):
    grant(client)
    response = client.put('/api/v1/research/background', json={'age_band': 'under18'})
    assert response.status_code == 200
    assert client.get('/api/v1/research/participation').json()['participating'] is False
    assert not read_authorized_database()['data']['enrollment']
