import copy
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.ml.lifestyle_evaluation import build_lifestyle_cases, run_lifestyle_ablation
from app.ml.lifestyle_report import METHODS, lifestyle_pipeline_fingerprint, read_lifestyle_report
from scripts.lifestyle_backtest import synthetic_event_data


def test_asof_cycle_and_daily_edits_do_not_rewrite_earlier_features():
    data = synthetic_event_data(n_users=1, n_cycles=8)
    cases, _ = build_lifestyle_cases(data['cycle_revisions'], data['daily_log_revisions'], data['cycle_tracking_events'])
    before = next(case for case in cases if case.elapsed == 0)
    modified = copy.deepcopy(data)
    daily = next(row for row in modified['daily_log_revisions'] if row['log_date'] < before.anchor)
    modified['daily_log_revisions'].append({**daily, 'revision_id': 99999,
        'known_at': before.issued_at + timedelta(days=1), 'payload': {'sleep_duration_minutes': 1, 'stress_level': 3}})
    cycle = modified['cycle_revisions'][0]
    modified['cycle_revisions'].append({**cycle, 'revision_id': 99999, 'end_date': cycle['start_date'] + timedelta(days=10),
                                      'known_at': before.issued_at + timedelta(days=1)})
    after = next(case for case in build_lifestyle_cases(modified['cycle_revisions'], modified['daily_log_revisions'], modified['cycle_tracking_events'])[0]
                 if case.key == before.key)
    for name in ('sleep_mean', 'stress_mean', 'lag_3_bleeding'):
        assert before.features[name] == after.features[name]


def test_backfilled_dates_and_unconfirmed_waiting_are_not_reconstructed():
    data = synthetic_event_data(n_users=1, n_cycles=8)
    cases, excluded = build_lifestyle_cases(data['cycle_revisions'], data['daily_log_revisions'])
    assert cases and all(case.elapsed == 0 for case in cases)
    assert excluded['dynamic_without_timely_confirmation'] > 0
    for event in data['cycle_revisions']:
        event['known_at'] = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert not build_lifestyle_cases(data['cycle_revisions'], data['daily_log_revisions'])[0]
    with pytest.raises(ValueError, match='No timely'):
        run_lifestyle_ablation(data['cycle_revisions'], data['daily_log_revisions'],
            calibration_cutoff='2022-06-01T00:00:00Z', test_cutoff='2022-09-01T00:00:00Z')


def test_purge_and_explicit_missed_tracking_change_eligibility_without_fake_dates():
    data = synthetic_event_data(n_users=1, n_cycles=8)
    cases, _ = build_lifestyle_cases(data['cycle_revisions'], data['daily_log_revisions'])
    first = cases[0]
    confirmation = {'event_id': 999, 'user_id': 1, 'cycle_id': first.cycle_id, 'anchor_start_date': first.anchor,
                    'kind': 'missed_tracking', 'as_of_date': first.anchor, 'known_at': first.label_known_at,
                    'timezone_name': 'Asia/Shanghai'}
    clean, counts = build_lifestyle_cases(data['cycle_revisions'], data['daily_log_revisions'], [confirmation])
    assert counts['confirmed_missed'] == 1 and first.key not in [case.key for case in clean]
    reset = {1: first.label_known_at}
    clean, counts = build_lifestyle_cases(data['cycle_revisions'], data['daily_log_revisions'], resets=reset)
    assert counts['purged_history'] > 0
    assert all(case.issued_at > first.label_known_at for case in clean)


@pytest.fixture(scope='module')
def paired_report():
    data = synthetic_event_data(n_users=3, n_cycles=16)
    return run_lifestyle_ablation(data['cycle_revisions'], data['daily_log_revisions'], data['cycle_tracking_events'],
        calibration_cutoff='2022-07-01T00:00:00Z', test_cutoff='2022-11-01T00:00:00Z', n_splits=3)


def test_same_cohort_all_variants_time_user_split_and_dynamic_confirmation(paired_report):
    json.dumps(paired_report, allow_nan=False)
    for stage in paired_report['stages'].values():
        for name, protocol in stage['protocols'].items():
            assert protocol['samples'] > 0
            assert set(protocol['metrics']) == set(METHODS)
            assert all(metric['samples'] == protocol['samples'] for metric in protocol['metrics'].values())
            ci = protocol['metrics']['sleep_stress_exercise_direct']['delta_mae_ci95']
            assert ci['n_users'] == 3 and not ci['available'] and 'lower' not in ci
            for fit in protocol['fits']:
                assert fit['training_labels_available_through'] <= paired_report['calibration_cutoff']
                assert fit['calibration_labels_available_through'] <= paired_report['test_cutoff']
                if name == 'unseen_users':
                    assert fit['held_out_user_overlap'] == 0
                for gate in fit['adaptive_blend'].values():
                    if gate['training_labels_available_through']:
                        assert gate['training_labels_available_through'] < gate['inner_cutoff']
                    if gate['validation_labels_available_through']:
                        assert gate['validation_labels_available_through'] <= paired_report['calibration_cutoff']
            for method in METHODS:
                assert sum(group[method]['samples'] for group in protocol['coverage_groups'].values()) == protocol['samples']
                assert sum(group[method]['samples'] for group in protocol['history_groups'].values()) == protocol['samples']
                assert sum(group[method]['samples'] for group in protocol['variability_groups'].values()) == protocol['samples']


def test_report_reader_strips_individual_data_and_rejects_mismatched_cohorts(paired_report, monkeypatch, tmp_path):
    from app.core.config import settings
    monkeypatch.setattr(settings, 'MODEL_PATH', tmp_path / 'model.skops')
    raw = {'schema_version': 1, 'metadata': {}, 'pipeline_sha256': lifestyle_pipeline_fingerprint(),
           'dataset': {'source': 'synthetic', 'n_users': 3}, 'evaluation': paired_report,
           'private_notes': ['not for administrators']}
    path = tmp_path / 'lifestyle_evaluation_report.json'
    path.write_text(json.dumps(raw), encoding='utf-8')
    sanitized = read_lifestyle_report()
    assert sanitized['available'] and 'private_notes' not in sanitized
    assert sanitized['pipeline_matches_report']
    assert sanitized['stages']['0']['protocols']['unseen_users']['metrics']['sleep_direct']['delta_mae_ci95']['n_users'] == 3
    raw['evaluation'] = copy.deepcopy(paired_report)
    raw['evaluation']['stages']['0']['protocols']['unseen_users']['metrics']['base_direct']['samples'] += 1
    path.write_text(json.dumps(raw), encoding='utf-8')
    assert not read_lifestyle_report()['available']


def test_reader_rejects_future_gate_labels_and_bad_personal_groups(paired_report, monkeypatch, tmp_path):
    from app.core.config import settings
    monkeypatch.setattr(settings, 'MODEL_PATH', tmp_path / 'model.skops')
    path = tmp_path / 'lifestyle_evaluation_report.json'
    for fault in ('future', 'partition'):
        report = copy.deepcopy(paired_report)
        protocol = report['stages']['0']['protocols']['existing_users']
        if fault == 'future':
            gate = protocol['fits'][0]['adaptive_blend']['base']
            gate['training_labels_available_through'] = gate['inner_cutoff']
        else:
            protocol['history_groups']['short']['base_adaptive']['samples'] += 1
        path.write_text(json.dumps({'schema_version': 1, 'metadata': {}, 'pipeline_sha256': lifestyle_pipeline_fingerprint(),
            'dataset': {'source': 'synthetic', 'n_users': 3}, 'evaluation': report}), encoding='utf-8')
        assert not read_lifestyle_report()['available']


def test_future_cycle_edits_and_annotations_cannot_rewrite_training_cohort(monkeypatch):
    from app.ml.lifestyle_evaluation import LifestyleCandidate, PARAMETERS
    monkeypatch.setitem(PARAMETERS, 'n_estimators', 4)
    data = synthetic_event_data(n_users=3, n_cycles=16)
    fitted = []
    original = LifestyleCandidate.fit
    def fit(self, cases):
        fitted.append([(case.key, case.actual_remaining) for case in cases])
        return original(self, cases)
    monkeypatch.setattr(LifestyleCandidate, 'fit', fit)
    args = {'calibration_cutoff': '2022-07-01T00:00:00Z', 'test_cutoff': '2022-11-01T00:00:00Z'}
    run_lifestyle_ablation(data['cycle_revisions'], data['daily_log_revisions'], data['cycle_tracking_events'], **args)
    before = copy.deepcopy(fitted)
    fitted.clear()
    past = data['cycle_revisions'][8]
    data['cycle_revisions'].append({**past, 'revision_id': 99999,
        'start_date': past['start_date'] + timedelta(days=1), 'known_at': datetime(2025, 1, 1, tzinfo=timezone.utc)})
    data['cycle_tracking_events'].append({'event_id': 99999, 'user_id': past['user_id'], 'cycle_id': past['cycle_id'],
        'anchor_start_date': past['start_date'], 'kind': 'missed_tracking', 'as_of_date': past['start_date'],
        'known_at': datetime(2025, 1, 2, tzinfo=timezone.utc), 'timezone_name': 'Asia/Shanghai'})
    run_lifestyle_ablation(data['cycle_revisions'], data['daily_log_revisions'], data['cycle_tracking_events'], **args)
    assert before == fitted
