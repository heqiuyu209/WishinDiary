import copy
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.ml.paired_uncertainty import paired_brier_interval
from app.ml.tracking_probability import build_tracking_cases, run_tracking_evaluation
from app.ml.tracking_report import sanitize_tracking_report
from scripts.lifestyle_backtest import evaluate_data, synthetic_event_data

END = '2024-01-01T00:00:00Z'
ARGS = {'calibration_cutoff': '2022-10-01T00:00:00Z', 'test_cutoff': '2023-04-01T00:00:00Z',
        'data_as_of': END, 'bootstrap_replicates': 200}


def test_only_explicit_later_reviews_label_closed_gaps_and_unknown_revokes_label():
    data = synthetic_event_data(1, 8)
    cases, counts = build_tracking_cases(data, END)
    assert cases and all(c.label is None for c in cases)
    assert counts['unreviewed_gaps'] == len(cases)
    first = cases[0]
    cycle = data['cycle_revisions'][0]
    review = {'event_id': 9999, 'user_id': 1, 'cycle_id': cycle['cycle_id'],
        'anchor_start_date': cycle['start_date'], 'kind': 'missed_tracking', 'as_of_date': first.issued_at.date(),
        'known_at': first.issued_at + timedelta(days=1), 'timezone_name': 'Asia/Shanghai'}
    data['cycle_tracking_events'].append(review)
    labelled = build_tracking_cases(data, END)[0][0]
    assert labelled.label == 1 and labelled.features == first.features
    boundary = review['known_at'] + timedelta(seconds=1)
    data['cycle_tracking_events'].append({**review, 'event_id': 10000, 'kind': 'unknown',
                                        'known_at': boundary + timedelta(days=1)})
    assert build_tracking_cases(data, boundary)[0][0].label == 1
    assert build_tracking_cases(data, END)[0][0].label is None


def test_future_revisions_do_not_change_issuance_features_or_past_fit_labels():
    data = synthetic_event_data(8, 22, tracking_scenarios=True)
    before = build_tracking_cases(data, END)[0]
    target = next(c for c in before if c.issued_at.year == 2023)
    old = next(row for row in data['daily_log_revisions'] if row['user_id'] == target.user_id and row['log_date'] < target.issued_at.date())
    changed = copy.deepcopy(data)
    changed['daily_log_revisions'].append({**old, 'revision_id': 999999,
        'known_at': target.issued_at + timedelta(days=1), 'payload': {'stress_level': 3}})
    after = next(c for c in build_tracking_cases(changed, END)[0] if c.key == target.key)
    assert target.features == after.features
    cutoff = datetime(2022, 10, 1, tzinfo=timezone.utc)
    old_reviews = [(c.key, c.label) for c in build_tracking_cases(data, cutoff)[0]]
    review = next(row for row in changed['cycle_tracking_events'] if row['kind'] == 'missed_tracking')
    changed['cycle_tracking_events'].append({**review, 'event_id': 999999, 'kind': 'unknown',
        'known_at': datetime(2025, 1, 1, tzinfo=timezone.utc)})
    assert old_reviews == [(c.key, c.label) for c in build_tracking_cases(changed, cutoff)[0]]


def test_tracking_probabilities_pair_constant_prior_with_no_held_user_leak():
    data = synthetic_event_data(12, 22, tracking_scenarios=True)
    result = run_tracking_evaluation(data, **ARGS)
    assert result['available']
    for name, protocol in result['protocols'].items():
        score = protocol['scores']
        assert score['samples'] > 0 and 0 <= score['brier'] <= 1
        assert protocol['unreviewed_samples'] > 0
        assert protocol['reviewed_samples'] == score['samples'] + protocol['skipped_reviewed_samples']
        assert sum(row['samples'] for row in score['reliability_bins']) == score['samples']
        assert score['delta_brier_ci95']['n_users'] == 12
        for fit in protocol['fits']:
            assert fit['training_labels_available_through'] <= ARGS['calibration_cutoff']
            if fit['calibration_labels_available_through']:
                assert fit['calibration_labels_available_through'] <= ARGS['test_cutoff']
            if name == 'unseen_users':
                assert fit['held_out_user_overlap'] == 0
        assert any(fit['probability_calibrated'] for fit in protocol['fits'])
    sanitized = sanitize_tracking_report(result, datetime.fromisoformat(ARGS['calibration_cutoff'].replace('Z', '+00:00')),
        datetime.fromisoformat(ARGS['test_cutoff'].replace('Z', '+00:00')))
    assert sanitized['available'] and 'parameters' not in sanitized
    assert 'user_id' not in str(sanitized) and 'case_key' not in str(sanitized)


def test_tracking_reader_rejects_future_labels_and_mismatched_bins():
    report = run_tracking_evaluation(synthetic_event_data(12, 22, tracking_scenarios=True), **ARGS)
    calibration, test = (datetime.fromisoformat(ARGS[key].replace('Z', '+00:00')) for key in ('calibration_cutoff', 'test_cutoff'))
    for fault in ('future', 'bins', 'denominator'):
        changed = copy.deepcopy(report)
        protocol = changed['protocols']['unseen_users']
        if fault == 'future':
            protocol['fits'][0]['training_labels_available_through'] = '2025-01-01T00:00:00Z'
        elif fault == 'bins':
            protocol['scores']['reliability_bins'][0]['samples'] += 1
        else:
            protocol['scores']['delta_brier_ci95']['samples'] += 1
        with pytest.raises(ValueError):
            sanitize_tracking_report(changed, calibration, test)


def test_tracking_enrollment_reset_and_underage_background_are_applied():
    data = synthetic_event_data(1, 8)
    cases, _ = build_tracking_cases(data, END)
    boundary = cases[3].issued_at
    data['enrollment'] = {1: boundary}
    kept, counts = build_tracking_cases(data, END)
    assert kept and all(c.issued_at >= boundary for c in kept) and counts['before_enrollment'] == 3
    data['resets'] = {1: boundary}
    kept, counts = build_tracking_cases(data, END)
    assert all(c.issued_at > boundary for c in kept) and counts['purged_history'] == 1
    data['research_background_revisions'] = [{'user_id': 1, 'revision_id': 1, 'known_at': boundary - timedelta(seconds=1),
        'payload': {'age_band': 'under18'}}]
    kept, counts = build_tracking_cases(data, END)
    assert not kept and counts['ineligible_age'] > 0


def test_unreviewed_data_and_sparse_classes_do_not_become_a_probability_model():
    result = run_tracking_evaluation(synthetic_event_data(3, 22), **ARGS)
    assert not result['available']
    assert all(p['scores']['samples'] == 0 for p in result['protocols'].values())


def test_closed_gap_research_can_run_when_all_cycle_forecasts_are_outside_scope(monkeypatch, tmp_path):
    from app.core.config import settings
    from app.ml.lifestyle_report import read_lifestyle_report
    data = synthetic_event_data(12, 22)
    data['cycle_revisions'] = [row for row in data['cycle_revisions'] if (row['cycle_id'] % 1000) % 2 == 0]
    data['cycle_tracking_events'] = []
    for user in range(1, 13):
        rows = [row for row in data['cycle_revisions'] if row['user_id'] == user and row['end_date'] is None]
        for index, (current, following) in enumerate(zip(rows, rows[1:])):
            data['cycle_tracking_events'].append({'event_id': len(data['cycle_tracking_events']) + 1,
                'user_id': user, 'cycle_id': current['cycle_id'], 'anchor_start_date': current['start_date'],
                'kind': 'missed_tracking' if index % 2 else 'true_long_interval',
                'as_of_date': following['start_date'] + timedelta(days=1), 'timezone_name': 'Asia/Shanghai',
                'known_at': following['known_at'] + timedelta(days=1)})
    report = evaluate_data(data, 'synthetic', **ARGS)
    assert report['evaluation']['eligible_cases'] == 0
    assert report['evaluation']['tracking_probability']['available']
    assert all(not stage['protocols']['unseen_users']['metrics'] for stage in report['evaluation']['stages'].values())
    # Individual rows and unexpected fields must not pass through the admin reader.
    report['evaluation']['tracking_probability']['private_rows'] = [{'user_id': 12345, 'case_key': 'sensitive'}]
    monkeypatch.setattr(settings, 'MODEL_PATH', tmp_path / 'model.skops')
    (tmp_path / 'lifestyle_evaluation_report.json').write_text(json.dumps(report, default=str), encoding='utf-8')
    sanitized = read_lifestyle_report()
    assert sanitized['available'] and sanitized['tracking_probability']['available']
    assert 'sensitive' not in json.dumps(sanitized) and 'user_id' not in json.dumps(sanitized)


def test_brier_interval_is_paired_squared_probability_loss():
    candidate = [{'user_id': i, 'case_key': str(i), 'point': 0, 'actual': 0} for i in range(12)]
    baseline = [{**row, 'point': 0.5} for row in candidate]
    result = paired_brier_interval(candidate, baseline, replicates=200)
    assert result['lower'] == result['upper'] == -0.25
    candidate[0]['point'] = 2
    with pytest.raises(ValueError, match='probability'):
        paired_brier_interval(candidate, baseline)
