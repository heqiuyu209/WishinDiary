"""Research-only lifestyle ablation. Never publishes weights or changes predictions."""
import argparse
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.core.database import transaction
from app.ml.lifestyle_evaluation import run_lifestyle_ablation
from app.ml.lifestyle_report import lifestyle_pipeline_fingerprint
from scripts.train import _collect_env_metadata


def synthetic_event_data(n_users=6, n_cycles=22):
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
    return {'cycle_revisions': cycles, 'daily_log_revisions': daily, 'cycle_tracking_events': tracking, 'resets': {}}


def read_authorized_database():
    result = {}
    with transaction() as connection:
        with connection.cursor() as cursor:
            for table in ('cycle_revisions', 'daily_log_revisions', 'cycle_tracking_events'):
                cursor.execute(f'SELECT * FROM {table} ORDER BY user_id LIMIT 1000001')
                rows = list(cursor.fetchall())
                if len(rows) > 1_000_000:
                    raise ValueError('Dataset too large; use a separately authorized bounded export')
                result[table] = rows
            cursor.execute('SELECT user_id,cycle_history_reset_at FROM users WHERE cycle_history_reset_at IS NOT NULL')
            result['resets'] = {row['user_id']: row['cycle_history_reset_at'] for row in cursor.fetchall()}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sources = parser.add_mutually_exclusive_group(required=True)
    sources.add_argument('--synthetic-only', action='store_true')
    sources.add_argument('--data-json', type=Path, help='Independently authorized event export, never plain date CSV')
    sources.add_argument('--database', action='store_true')
    parser.add_argument('--acknowledge-authorized-data', action='store_true')
    parser.add_argument('--calibration-cutoff', default='2022-10-01T00:00:00Z', help='Timezone-aware ISO timestamp')
    parser.add_argument('--test-cutoff', default='2023-04-01T00:00:00Z', help='Timezone-aware ISO timestamp')
    parser.add_argument('--data-as-of', default=None, help='Freeze observed events at this ISO timestamp; defaults to current UTC')
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    if not args.synthetic_only and not args.acknowledge_authorized_data:
        parser.error('Real data requires independent authorization and --acknowledge-authorized-data')
    if args.synthetic_only:
        data, source = synthetic_event_data(), 'synthetic'
    elif args.data_json:
        if args.data_json.stat().st_size > 100_000_000:
            parser.error('Event export too large')
        data, source = json.loads(args.data_json.read_text(encoding='utf-8')), 'authorized_event_json'
        if 'user' in data:
            data['resets'] = {data['user']['user_id']: data['user'].get('cycle_history_reset_at')}
    else:
        data, source = read_authorized_database(), 'authorized_database'
    for value in (args.calibration_cutoff, args.test_cutoff, *([args.data_as_of] if args.data_as_of else [])):
        if datetime.fromisoformat(value.replace('Z', '+00:00')).tzinfo is None:
            parser.error('Cutoffs require explicit timezone offsets')
    resets = {int(key): value for key, value in data.get('resets', {}).items() if value}
    report = {'schema_version': 1, 'metadata': _collect_env_metadata(),
        'pipeline_sha256': lifestyle_pipeline_fingerprint(),
        'dataset': {'source': source, 'cycle_events': len(data['cycle_revisions']),
                    'daily_events': len(data['daily_log_revisions']),
                    'n_users': len({row['user_id'] for row in data['cycle_revisions']}),
                    'fingerprint': hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()},
        'evaluation': run_lifestyle_ablation(data['cycle_revisions'], data['daily_log_revisions'],
            data.get('cycle_tracking_events', []), resets, calibration_cutoff=args.calibration_cutoff,
            test_cutoff=args.test_cutoff, data_as_of=args.data_as_of),
        'notes': ['Research candidate only; no weights are published and no online prediction changes.',
                  'All feature groups and shrinkage modes share each protocol/stage test cohort.',
                  'Cycle and daily events must be known before forecast issuance. Legacy/backfilled forecasts are not reconstructed.',
                  'Dynamic stages require a timely explicit no-onset confirmation; absence of a log is not confirmation.',
                  'Median imputation is fitted on training only; missingness and calendar-day coverage remain explicit.',
                  'Intervals use a separate chronological calibration segment; 90% is a target, not a clinical or IID coverage guarantee.',
                  'Synthetic effects demonstrate a workflow, not medical causality or real accuracy.']}
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
