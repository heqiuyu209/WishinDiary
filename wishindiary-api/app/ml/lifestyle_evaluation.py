"""Offline paired ablation with cycle/daily events known at each issuance time."""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from fractions import Fraction
import hashlib
import math
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline

from app.features.cycle_feature_engineering import prepare_ml_history
from app.features.lifestyle_features import (
    FEATURE_GROUPS, LIFESTYLE_FEATURE_VERSION, build_research_feature_row, utc_instant,
)
from app.ml.prediction_scope import history_is_supported

STAGES = (0, 7, 14, 21)
PARAMETERS = {'n_estimators': 80, 'max_depth': 8, 'random_state': 42}


def calendar_date(value):
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(value) if isinstance(value, str) else value


def cycle_rows_as_of(events, as_of):
    selected = {}
    for raw in events:
        row = {**raw, 'known_at': utc_instant(raw['known_at']),
               'start_date': calendar_date(raw['start_date']), 'end_date': calendar_date(raw.get('end_date'))}
        if row['known_at'] >= as_of:
            continue
        key = (int(row['user_id']), int(row['cycle_id']))
        rank = (row['known_at'], int(row['revision_id']))
        if key not in selected or rank > selected[key][0]:
            selected[key] = (rank, row)
    rows = [value[1] for value in selected.values()]
    if len({(row['user_id'], row['start_date']) for row in rows}) != len(rows):
        raise ValueError('Duplicate as-of cycle starts')
    return sorted(rows, key=lambda row: (row['user_id'], row['start_date']))


@dataclass
class LifestyleCase:
    user_id: int
    cycle_id: int
    anchor: date
    issued_at: datetime
    label_known_at: datetime
    elapsed: int
    actual_remaining: float
    history: pd.DataFrame
    features: dict

    @property
    def key(self):
        return f'{self.user_id}/{self.cycle_id}/{self.anchor}/{self.elapsed}/{self.issued_at.isoformat()}'


def build_lifestyle_cases(cycle_events, daily_events, tracking_events=(), resets=None, *, dataset_as_of=None):
    """No created_at guesses or synthetic dates for real backfilled observations."""
    resets = resets or {}
    end = utc_instant(dataset_as_of) if dataset_as_of else datetime.max.replace(tzinfo=timezone.utc)
    final = cycle_rows_as_of(cycle_events, end)
    tracking = [{**row, 'known_at': utc_instant(row['known_at']),
                 'anchor_start_date': calendar_date(row['anchor_start_date']),
                 'as_of_date': calendar_date(row['as_of_date'])} for row in tracking_events
                if utc_instant(row['known_at']) < end]
    counts = {key: 0 for key in ('candidate_intervals', 'late_or_unknown_issuance', 'edited_anchor',
                                'purged_history', 'unsupported_history', 'missing_history', 'confirmed_missed',
                                'dynamic_without_timely_confirmation')}
    cases = []
    for user_id in sorted({int(row['user_id']) for row in final}):
        rows = [row for row in final if int(row['user_id']) == user_id]
        user_cycles = [row for row in cycle_events if int(row['user_id']) == user_id and utc_instant(row['known_at']) < end]
        user_daily = [row for row in daily_events if int(row['user_id']) == user_id]
        user_tracking = [row for row in tracking if int(row['user_id']) == user_id]
        def versions(cycle):
            return [row for row in user_cycles if int(row['cycle_id']) == int(cycle['cycle_id'])]
        def missed(anchor, cutoff):
            items = [row for row in user_tracking if row['anchor_start_date'] == anchor
                     and row['kind'] != 'no_onset' and row['known_at'] < cutoff]
            return bool(items and max(items, key=lambda row: (row['known_at'], int(row['event_id'])))['kind'] == 'missed_tracking')
        for current, following in zip(rows, rows[1:]):
            counts['candidate_intervals'] += 1
            cv, fv = versions(current), versions(following)
            if any(len({calendar_date(row['start_date']) for row in items}) > 1 for items in (cv, fv)):
                counts['edited_anchor'] += 1
                continue
            issued_events = [row for row in cv if row['source'] == 'user_recorded']
            if not issued_events:
                counts['late_or_unknown_issuance'] += 1
                continue
            first = min(issued_events, key=lambda row: (utc_instant(row['known_at']), int(row['revision_id'])))
            issued = utc_instant(first['known_at']) + timedelta(microseconds=1)
            label_known = min(utc_instant(row['known_at']) for row in fv)
            tz = first['timezone_name']
            actual_day = datetime.combine(following['start_date'], time.min, ZoneInfo(tz)).astimezone(timezone.utc)
            anchor_day = datetime.combine(current['start_date'], time.min, ZoneInfo(tz)).astimezone(timezone.utc)
            if not anchor_day <= issued < actual_day or label_known <= issued or issued.astimezone(ZoneInfo(tz)).date() != current['start_date']:
                counts['late_or_unknown_issuance'] += 1
                continue
            # Outcome annotation is not inferred from gap size. Missing onsets
            # cannot be treated as reliable labels for any variant.
            if missed(current['start_date'], end):
                counts['confirmed_missed'] += 1
                continue
            for stage in STAGES:
                as_of = issued
                if stage:
                    confirmed_day = current['start_date'] + timedelta(days=stage)
                    matches = [row for row in user_tracking if row['kind'] == 'no_onset'
                               and row['anchor_start_date'] == current['start_date']
                               and row['as_of_date'] == confirmed_day
                               and row['known_at'].astimezone(ZoneInfo(row['timezone_name'])).date() == confirmed_day]
                    if not matches:
                        counts['dynamic_without_timely_confirmation'] += 1
                        continue
                    as_of = min(row['known_at'] for row in matches) + timedelta(microseconds=1)
                    if not issued <= as_of < actual_day or label_known <= as_of:
                        continue
                reset = resets.get(user_id)
                if reset and as_of <= utc_instant(reset):
                    counts['purged_history'] += 1
                    continue
                snapshot = cycle_rows_as_of(user_cycles, as_of)
                history = []
                for previous, next_row in zip(snapshot, snapshot[1:]):
                    if next_row['start_date'] > current['start_date']:
                        continue
                    if missed(previous['start_date'], as_of):
                        continue
                    duration = ((previous['end_date'] - previous['start_date']).days + 1
                                if previous['end_date'] is not None else None)
                    history.append({'start_date': previous['start_date'],
                                    'cycle_length': (next_row['start_date'] - previous['start_date']).days,
                                    'bleeding_days': duration})
                if not history_is_supported(history):
                    counts['unsupported_history'] += 1
                    continue
                clean = prepare_ml_history(pd.DataFrame(history, columns=['start_date', 'cycle_length', 'bleeding_days']))
                if len(clean) < 3:
                    counts['missing_history'] += 1
                    continue
                feature = build_research_feature_row(clean, user_daily, user_id=user_id,
                    anchor=current['start_date'], as_of=as_of, timezone_name=tz, elapsed_days=stage)
                cases.append(LifestyleCase(user_id, int(current['cycle_id']), current['start_date'], as_of,
                    label_known, stage, float((following['start_date'] - current['start_date']).days - stage), clean, feature))
    return sorted(cases, key=lambda case: (case.issued_at, case.user_id, case.elapsed)), counts


class LifestyleCandidate:
    """Research-only estimator; feature contract is separate from online v2."""
    version = LIFESTYLE_FEATURE_VERSION

    def __init__(self, group):
        self.names = FEATURE_GROUPS[group]
        self.model = make_pipeline(SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True),
                                   RandomForestRegressor(**PARAMETERS))

    def fit(self, cases):
        self.model.fit(pd.DataFrame([case.features for case in cases], columns=self.names),
                       [case.actual_remaining for case in cases])
        return self

    def predict(self, cases, *, shrinkage=False):
        raw = self.model.predict(pd.DataFrame([case.features for case in cases], columns=self.names))
        if shrinkage:
            weights = np.array([1 / (1 + len(case.history) / 4) for case in cases])
            prior = np.array([max(1, float(case.history.cycle_length.mean()) - case.elapsed) for case in cases])
            raw = weights * raw + (1 - weights) * prior
        return np.maximum(1, np.rint(raw))


def _scores(rows):
    if not rows:
        return {'samples': 0}
    error = np.array([row['point'] - row['actual'] for row in rows])
    intervals = [row for row in rows if row['radius'] is not None]
    result = {'samples': len(rows), 'mae': round(float(np.abs(error).mean()), 4),
              'hit_rate_within_2d': round(float((np.abs(error) <= 2).mean() * 100), 2),
              'interval_samples': len(intervals), 'interval_unavailable_samples': len(rows) - len(intervals)}
    if intervals:
        result.update(coverage_pct=round(100 * sum(abs(row['point'] - row['actual']) <= row['radius'] for row in intervals) / len(intervals), 2),
                      mean_width_days=round(float(np.mean([2 * row['radius'] for row in intervals])), 4))
    return result


def run_lifestyle_ablation(cycle_events, daily_events, tracking_events=(), resets=None, *, calibration_cutoff,
                           test_cutoff, n_splits=3, coverage=0.9, data_as_of=None):
    calibration_cutoff, test_cutoff = utc_instant(calibration_cutoff), utc_instant(test_cutoff)
    if calibration_cutoff >= test_cutoff or not 2 <= n_splits <= 10 or not 0 < coverage < 1:
        raise ValueError('Invalid research cutoffs, folds or coverage')
    data_as_of = utc_instant(data_as_of or datetime.now(timezone.utc))
    if data_as_of <= test_cutoff:
        raise ValueError('Data snapshot must follow the test cutoff')
    cases, exclusions = build_lifestyle_cases(cycle_events, daily_events, tracking_events, resets, dataset_as_of=data_as_of)
    # Build labels/cohorts as actually known at each fit cutoff. Future start
    # edits or missed-tracking annotations must not remove/rewrite old fits.
    train_snapshot, _ = build_lifestyle_cases(cycle_events, daily_events, tracking_events, resets, dataset_as_of=calibration_cutoff)
    calibration_snapshot, _ = build_lifestyle_cases(cycle_events, daily_events, tracking_events, resets, dataset_as_of=test_cutoff)
    if not cases:
        raise ValueError('No timely as-recorded cases with sufficient history; backfilled dates cannot reconstruct past forecasts')
    probability = Fraction(str(coverage))
    output = {}
    for stage in STAGES:
        selected = [case for case in cases if case.elapsed == stage]
        train = [case for case in train_snapshot if case.elapsed == stage and case.issued_at < calibration_cutoff and case.label_known_at <= calibration_cutoff
                 and 21 <= case.actual_remaining + stage <= 45]
        calibration = [case for case in calibration_snapshot if case.elapsed == stage and calibration_cutoff <= case.issued_at < test_cutoff and case.label_known_at <= test_cutoff]
        targets = [case for case in selected if case.issued_at >= test_cutoff]
        protocols = {}
        seen = {case.user_id for case in train}
        existing = [case for case in targets if case.user_id in seen]
        folds = [('existing_users', train, calibration, existing)]
        users = sorted({case.user_id for case in selected})
        if len(users) >= 2:
            for _, indices in GroupKFold(n_splits=min(n_splits, len(users))).split(np.zeros((len(users), 1)), groups=users):
                held = {users[int(index)] for index in indices}
                folds.append(('unseen_users', [case for case in train if case.user_id not in held],
                              [case for case in calibration if case.user_id not in held],
                              [case for case in targets if case.user_id in held]))
        for name in ('existing_users', 'unseen_users'):
            records, cohort, fitted = {}, [], []
            skipped = 0
            for protocol, prefix, cal, test in folds:
                if protocol != name:
                    continue
                if not prefix or not test:
                    skipped += 1
                    continue
                cohort.extend(test)
                fitted.append({'training_samples': len(prefix), 'calibration_samples': len(cal),
                    'training_labels_available_through': max(case.label_known_at for case in prefix).isoformat(),
                    'calibration_labels_available_through': max((case.label_known_at for case in cal), default=None).isoformat() if cal else None,
                    'held_out_user_overlap': len({c.user_id for c in prefix} & {c.user_id for c in test}) if name == 'unseen_users' else None})
                def save(method, points, calibration_points):
                    errors = sorted(abs(float(point) - case.actual_remaining) for point, case in zip(calibration_points, cal))
                    rank = math.ceil((len(errors) + 1) * probability)
                    radius = errors[rank - 1] if rank <= len(errors) else None
                    rows = records.setdefault(method, [])
                    rows.extend({'point': float(point), 'actual': case.actual_remaining, 'radius': radius,
                                 'coverage': np.mean([case.features[f'{group}_coverage'] for group in ('sleep', 'stress', 'exercise')])}
                                for point, case in zip(points, test))
                for group in FEATURE_GROUPS:
                    model = LifestyleCandidate(group).fit(prefix)
                    for shrinkage in (False, True):
                        save(group + ('_shrinkage' if shrinkage else '_direct'),
                             model.predict(test, shrinkage=shrinkage), model.predict(cal, shrinkage=shrinkage) if cal else [])
                for method in ('mean3', 'median3', 'ewma'):
                    def points(values):
                        result = []
                        for case in values:
                            lengths = case.history.cycle_length.to_numpy(dtype=float)
                            value = np.mean(lengths[-3:]) if method == 'mean3' else np.median(lengths[-3:])
                            if method == 'ewma':
                                value = lengths[0]
                                for length in lengths[1:]:
                                    value = 0.5 * length + 0.5 * value
                            result.append(max(1, round(float(value) - stage)))
                        return result
                    save(method, points(test), points(cal))
            metrics = {method: _scores(rows) for method, rows in records.items()}
            for method, metric in metrics.items():
                if method.endswith(('_direct', '_shrinkage')):
                    baseline = 'base_' + method.rsplit('_', 1)[1]
                    metric['delta_mae_vs_base'] = round(metric['mae'] - metrics[baseline]['mae'], 4)
            protocols[name] = {'samples': len(cohort), 'candidate_samples': len(existing) if name == 'existing_users' else len(targets),
                'excluded_unseen_cases': len(targets) - len(existing) if name == 'existing_users' else 0,
                'skipped_empty_folds': skipped, 'fits': fitted,
                'cohort_sha256': hashlib.sha256('\n'.join(sorted(case.key for case in cohort)).encode()).hexdigest(),
                'metrics': metrics, 'coverage_groups': {
                    bucket: {method: _scores([row for row in rows if include(row['coverage'])]) for method, rows in records.items()}
                    for bucket, include in [('none', lambda value: value == 0), ('sparse', lambda value: 0 < value < 0.5),
                                            ('covered', lambda value: value >= 0.5)]}}
        output[str(stage)] = {'target': 'cycle_length_days' if not stage else 'remaining_wait_days', 'protocols': protocols}
    return {'feature_version': LIFESTYLE_FEATURE_VERSION, 'data_as_of': data_as_of.isoformat(), 'calibration_cutoff': calibration_cutoff.isoformat(),
            'test_cutoff': test_cutoff.isoformat(), 'target_coverage_pct': coverage * 100,
            'parameters': {'rf': PARAMETERS, 'window_days': 28, 'shrinkage_k': 4, 'stages': list(STAGES)},
            'eligible_cases': len(cases), 'exclusions': exclusions, 'stages': output}
