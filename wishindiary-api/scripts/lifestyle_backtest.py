"""Research-only lifestyle ablation. Never publishes weights or changes predictions."""
import argparse
from datetime import date, datetime, time, timedelta, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.ml.lifestyle_evaluation import run_lifestyle_ablation
from app.ml.lifestyle_report import lifestyle_pipeline_fingerprint
from app.ml.tracking_probability import run_tracking_evaluation
from app.services.research_dataset_service import (
    authorization_is_current, fingerprint, read_authorized_database, report_authorization, validate_snapshot,
)
from scripts.train import _collect_env_metadata


def synthetic_event_data(n_users=6, n_cycles=22, *, tracking_scenarios=False):
    cycles, daily, tracking = [], [], []
    revision_id = 0
    for user_id in range(1, n_users + 1):
        anchor = date(2022, 1, 1)
        starts = [anchor]
        for index in range(n_cycles + 1):
            cycle_id = user_id * 1000 + index
            revision_id += 1
            cycles.append({'revision_id': revision_id, 'cycle_id': cycle_id, 'user_id': user_id,
                'start_date': anchor, 'end_date': None, 'source': 'user_recorded', 'timezone_name': 'Asia/Shanghai',
                'known_at': datetime.combine(anchor, time(8), timezone.utc)})
            revision_id += 1
            cycles.append({**cycles[-1], 'revision_id': revision_id, 'end_date': anchor + timedelta(days=4),
                'known_at': datetime.combine(anchor + timedelta(days=4), time(9), timezone.utc)})
            if index == n_cycles:
                break
            stress = ((anchor.toordinal() // 7) + user_id) % 4
            length = 25 + user_id % 6 + stress + (index % 3 - 1)
            if tracking_scenarios and index % 8 == 3:
                # A genuinely long synthetic interval, distinct from omitted tracking.
                length += 25
            for stage in (7, 14, 21):
                if stage < length:
                    observed = anchor + timedelta(days=stage)
                    tracking.append({'event_id': len(tracking) + 1, 'cycle_id': cycle_id, 'user_id': user_id,
                        'anchor_start_date': anchor, 'kind': 'no_onset', 'as_of_date': observed,
                        'known_at': datetime.combine(observed, time(9), timezone.utc), 'timezone_name': 'Asia/Shanghai'})
            anchor += timedelta(days=length)
            starts.append(anchor)
        day = starts[0] - timedelta(days=28)
        while day < starts[-1]:
            if day.toordinal() % (user_id + 2) != 0:
                stress = ((day.toordinal() // 7) + user_id) % 4
                missing = user_id % 3 == 0
                payload = {name: None for name in ('sleep_duration_minutes', 'sleep_start_minutes', 'sleep_quality',
                    'is_late_night', 'is_night_shift', 'stress_level', 'is_exercise', 'exercise_minutes', 'exercise_intensity')}
                if not missing:
                    active = day.toordinal() % 3 != 0
                    payload.update(sleep_duration_minutes=480 - stress * 30, sleep_start_minutes=(1380 + stress * 30) % 1440,
                        sleep_quality=3 - stress, is_late_night=stress >= 2, is_night_shift=False, stress_level=stress,
                        is_exercise=active, exercise_minutes=30 if active else 0, exercise_intensity=2 if active else 0)
                daily.append({'revision_id': len(daily) + 1, 'user_id': user_id, 'log_date': day,
                    'known_at': datetime.combine(day + timedelta(days=1), time(0), timezone.utc),
                    'source': 'user_recorded', 'timezone_name': 'Asia/Shanghai', 'payload': payload})
            day += timedelta(days=1)
    if tracking_scenarios:
        omitted = {row['cycle_id'] for row in cycles
                   if ((row['cycle_id'] % 1000) + row['user_id'] % 3) % 7 == 5}
        cycles = [row for row in cycles if row['cycle_id'] not in omitted]
        tracking = [row for row in tracking if row['cycle_id'] not in omitted]
        for user_id in range(1, n_users + 1):
            rows = [row for row in cycles if row['user_id'] == user_id and row['end_date'] is None]
            for index, (current, following) in enumerate(zip(rows, rows[1:])):
                kind = 'missed_tracking' if following['cycle_id'] - current['cycle_id'] > 1 else 'true_long_interval'
                if index % 5 == 4 and kind != 'missed_tracking':
                    continue  # Deliberately unreviewed, never a negative label.
                tracking.append({'event_id': max((row['event_id'] for row in tracking), default=0) + 1,
                    'cycle_id': current['cycle_id'], 'user_id': user_id, 'anchor_start_date': current['start_date'],
                    'kind': kind, 'as_of_date': following['start_date'] + timedelta(days=1),
                    'known_at': datetime.combine(following['start_date'] + timedelta(days=1), time(9), timezone.utc),
                    'timezone_name': 'Asia/Shanghai'})
    return {'cycle_revisions': cycles, 'daily_log_revisions': daily, 'cycle_tracking_events': tracking, 'resets': {}}


def evaluate_data(data, source, *, calibration_cutoff, test_cutoff, data_as_of=None,
                  authorization=None, bootstrap_replicates=1000):
    resets = {int(key): value for key, value in data.get('resets', {}).items() if value}
    report = {'schema_version': 1, 'metadata': _collect_env_metadata(),
        'pipeline_sha256': lifestyle_pipeline_fingerprint(),
        'dataset': {'source': source, 'cycle_events': len(data['cycle_revisions']),
                    'daily_events': len(data['daily_log_revisions']),
                    'n_users': len({row['user_id'] for row in data['cycle_revisions']}),
                    'fingerprint': fingerprint(data)},
        'evaluation': run_lifestyle_ablation(data['cycle_revisions'], data['daily_log_revisions'],
            data.get('cycle_tracking_events', []), resets, calibration_cutoff=calibration_cutoff,
            test_cutoff=test_cutoff, data_as_of=data_as_of, bootstrap_replicates=bootstrap_replicates,
            enrollment=data.get('enrollment'), background_events=data.get('research_background_revisions', [])),
        'notes': ['Research candidate only; no weights are published and no online prediction changes.',
                  'All feature groups and shrinkage modes share each protocol/stage test cohort.',
                  'Cycle and daily events must be known before forecast issuance. Legacy/backfilled forecasts are not reconstructed.',
                  'Dynamic stages require a timely explicit no-onset confirmation; absence of a log is not confirmation.',
                  'Median imputation is fitted on training only; missingness and calendar-day coverage remain explicit.',
                  'Intervals use a separate chronological calibration segment; 90% is a target, not a clinical or IID coverage guarantee.',
                  'Paired MAE percentile intervals cluster whole users, conditional on fitted models. Exploratory comparisons are unadjusted.',
                  'Synthetic effects demonstrate a workflow, not medical causality or real accuracy.']}
    report['evaluation']['tracking_probability'] = run_tracking_evaluation(data,
        calibration_cutoff=calibration_cutoff, test_cutoff=test_cutoff,
        data_as_of=report['evaluation']['data_as_of'], bootstrap_replicates=bootstrap_replicates)
    report['notes'].extend([
        'Adaptive weights use a nested chronological segment of training; calibration remains for interval radii.',
        'Conditional history waiting uses timely no-onset confirmations, never absence of logging.',
        'Closed-gap probabilities target later explicit user reviews; unknown/unreviewed gaps are unlabelled.',
        'Probability evaluation is selective to reviewed gaps, not latent biological truth or a validated user reminder.'])
    if authorization:
        if not authorization_is_current(authorization):
            raise ValueError('Consent changed during evaluation; discard the run and create a new snapshot')
        report['authorization'] = authorization
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sources = parser.add_mutually_exclusive_group(required=True)
    sources.add_argument('--synthetic-only', action='store_true')
    sources.add_argument('--data-json', type=Path, help='Signed research snapshot with current in-app consent')
    sources.add_argument('--database', action='store_true')
    parser.add_argument('--acknowledge-authorized-data', action='store_true')
    parser.add_argument('--calibration-cutoff', default='2022-10-01T00:00:00Z', help='Timezone-aware ISO timestamp')
    parser.add_argument('--test-cutoff', default='2023-04-01T00:00:00Z', help='Timezone-aware ISO timestamp')
    parser.add_argument('--data-as-of', default=None, help='Freeze observed events at this ISO timestamp; defaults to current UTC')
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    authorization = None
    if not args.synthetic_only and not args.acknowledge_authorized_data:
        parser.error('Real data requires independent authorization and --acknowledge-authorized-data')
    if args.synthetic_only:
        data, source = synthetic_event_data(tracking_scenarios=True), 'synthetic'
    elif args.data_json:
        if args.data_json.stat().st_size > 100_000_000:
            parser.error('Event export too large')
        snapshot = json.loads(args.data_json.read_text(encoding='utf-8'))
        data, source = validate_snapshot(snapshot), 'authorized_event_json'
        authorization = report_authorization(snapshot)
    else:
        snapshot = read_authorized_database()
        data, source = snapshot['data'], 'authorized_database'
        authorization = report_authorization(snapshot)
    for value in (args.calibration_cutoff, args.test_cutoff, *([args.data_as_of] if args.data_as_of else [])):
        if datetime.fromisoformat(value.replace('Z', '+00:00')).tzinfo is None:
            parser.error('Cutoffs require explicit timezone offsets')
    report = evaluate_data(data, source, calibration_cutoff=args.calibration_cutoff, test_cutoff=args.test_cutoff,
                           data_as_of=args.data_as_of, authorization=authorization)
    directory = args.output_dir or settings.model_abs_path.parent
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'lifestyle_evaluation_report.json'
    payload = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(payload, encoding='utf-8')
    temporary.replace(path)
    print(f'Research report: {path}; source={source}; eligible={report["evaluation"]["eligible_cases"]}')


if __name__ == '__main__':
    main()
