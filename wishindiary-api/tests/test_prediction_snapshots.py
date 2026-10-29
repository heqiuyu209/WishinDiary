"""Forecast evaluation must never choose a prediction using the actual result."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest

from app.core.database import transaction
from app.repositories.prediction_log_repository import insert_prediction_snapshot
from app.services.cycle_service import CycleService
from app.services.report_service import ReportService


def _seed(client):
    assert client.post('/api/v1/auth/register', json={
        'username': 'snapshot_user', 'password': 'password123',
    }).status_code == 200
    client.post('/api/v1/auth/login', json={'username': 'snapshot_user', 'password': 'password123'})
    user_id = client.get('/api/v1/auth/session').json()['user_id']
    with transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO cycles (user_id, start_date, end_date) VALUES (%s,'2024-01-01','2024-01-05')", (user_id,))
    return user_id


def _store(user_id, predicted='2024-01-29', version='first-model'):
    prediction = {'last_period_start': '2024-01-01', 'next_period_start': predicted,
                  'model_version': version, 'confidence_interval': {'low': 26, 'high': 30}}
    with transaction() as connection:
        with connection.cursor() as cursor:
            insert_prediction_snapshot(cursor, user_id, prediction, method='rf_personalized', model_sha256='a' * 64)


def _logs(user_id):
    with transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT * FROM prediction_logs WHERE user_id = %s ORDER BY pred_id', (user_id,))
            return cursor.fetchall()


def _issue_at(user_id, issued_at):
    with transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute('UPDATE prediction_logs SET issued_at = %s WHERE user_id = %s AND anchor_start_date IS NOT NULL', (issued_at, user_id))


def test_refresh_and_model_change_do_not_replace_first_snapshot(client):
    user_id = _seed(client)
    _store(user_id)
    first = _logs(user_id)[0]
    _store(user_id, '2024-01-31', 'replacement-model')
    assert _logs(user_id) == [first]
    assert first['model_sha256'] == 'a' * 64
    assert first['interval_low'] == 26


def test_reconciliation_uses_anchor_not_closest_prediction(client):
    user_id = _seed(client)
    _store(user_id)
    _issue_at(user_id, '2024-01-02 00:00:00')
    with transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO prediction_logs (user_id, predicted_date) VALUES (%s,'2024-01-31')", (user_id,))
    CycleService().log_start(user_id, date(2024, 1, 31))
    snapshot, legacy = _logs(user_id)
    assert snapshot['actual_date'] == date(2024, 1, 31)
    assert snapshot['error_days'] == 2
    assert legacy['actual_date'] is None


@pytest.mark.parametrize('issued_at,eligible', [
    ('2024-01-30 15:59:59.999999', True),
    ('2024-01-30 16:00:00', False),  # Jan 31 00:00 in Asia/Shanghai
    ('2024-02-01 00:00:00', False),  # retrospectively recording an actual start
])
def test_local_actual_day_and_retrospective_forecasts_are_excluded(client, issued_at, eligible):
    user_id = _seed(client)
    _store(user_id)
    _issue_at(user_id, issued_at)
    CycleService().log_start(user_id, date(2024, 1, 31))
    assert (_logs(user_id)[0]['actual_date'] is not None) is eligible


def test_concurrent_predictions_only_claim_one_snapshot(client):
    user_id = _seed(client)
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda prediction: _store(user_id, prediction), ['2024-01-29', '2024-01-31']))
    assert len(_logs(user_id)) == 1


def test_prediction_computed_before_anchor_changed_is_not_recorded(client):
    user_id = _seed(client)
    CycleService().log_start(user_id, date(2024, 1, 31))
    _store(user_id)
    assert not _logs(user_id)


def test_zero_mae_survives_and_edited_outcomes_are_excluded(client):
    user_id = _seed(client)
    _store(user_id)
    _issue_at(user_id, '2024-01-02 00:00:00')
    CycleService().log_start(user_id, date(2024, 1, 29))
    with transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO prediction_logs (user_id, predicted_date, actual_date) VALUES (%s,'2024-01-01','2024-01-10')", (user_id,))
    report = ReportService().get_report(user_id)['report']
    assert report['ai_prediction_accuracy_days'] == 0
    assert report['latest_prediction_error_days'] == 0
    with transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE cycles SET start_date = '2024-01-31' WHERE user_id = %s AND start_date = '2024-01-29'", (user_id,))
    assert ReportService().get_report(user_id)['report']['ai_prediction_accuracy_days'] == '尚无对账样本'
