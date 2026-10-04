"""Offline probability of an explicitly reviewed closed gap being missed tracking.

This target is the user's later review, not latent biological onset or clinical
truth. Unreviewed/unknown gaps never become negative labels. No dates are imputed.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.features.lifestyle_features import build_lifestyle_features, utc_instant
from app.features.research_background import background_as_of, background_group
from app.ml.lifestyle_evaluation import calendar_date, cycle_rows_as_of
from app.ml.paired_uncertainty import paired_brier_interval

TRACKING_VERSION = 'closed-gap-tracking-v1'
FEATURES = ('observed_gap_days', 'history_count', 'personal_median', 'personal_iqr',
            'gap_to_personal_ratio', 'daily_coverage')
TRACKING_PARAMETERS = {'min_training_samples': 20, 'min_class_samples': 5, 'min_training_users': 3,
    'min_calibration_samples': 20, 'logistic_c': 1, 'max_iter': 1000,
    'seed': 42, 'solver': 'liblinear', 'standardize': True,
    'probability_bins': [0, 0.2, 0.4, 0.6, 0.8, 1], 'features': list(FEATURES)}


@dataclass
class TrackingCase:
    user_id: int
    key: str
    issued_at: datetime
    label_known_at: datetime | None
    label: int | None
    features: dict


def build_tracking_cases(data, as_of):
    cutoff = utc_instant(as_of)
    events = data['cycle_revisions']
    final = cycle_rows_as_of(events, cutoff)
    tracking = [row for row in data.get('cycle_tracking_events', []) if utc_instant(row['known_at']) < cutoff]
    enrollment = {int(key): utc_instant(value) for key, value in data.get('enrollment', {}).items()}
    resets = {int(key): utc_instant(value) for key, value in data.get('resets', {}).items() if value}
    counts = {key: 0 for key in ('candidate_intervals', 'edited_anchor', 'late_or_unknown_issuance',
        'before_enrollment', 'purged_history', 'ineligible_age', 'outcome_already_known', 'unreviewed_gaps')}
    cases = []
    for user_id in sorted({int(row['user_id']) for row in final}):
        rows = [row for row in final if int(row['user_id']) == user_id]
        user_events = [row for row in events if int(row['user_id']) == user_id and utc_instant(row['known_at']) < cutoff]
        user_tracking = [row for row in tracking if int(row['user_id']) == user_id]
        for current, following in zip(rows, rows[1:]):
            counts['candidate_intervals'] += 1
            versions = [[row for row in user_events if int(row['cycle_id']) == int(cycle['cycle_id'])]
                        for cycle in (current, following)]
            if any(len({calendar_date(row['start_date']) for row in items}) > 1 for items in versions):
                counts['edited_anchor'] += 1
                continue
            recorded = [row for row in versions[1] if row['source'] == 'user_recorded']
            first = min(recorded, key=lambda row: (utc_instant(row['known_at']), int(row['revision_id']))) if recorded else None
            if not first or utc_instant(first['known_at']).astimezone(ZoneInfo(first['timezone_name'])).date() != following['start_date']:
                counts['late_or_unknown_issuance'] += 1
                continue
            issued = utc_instant(first['known_at']) + timedelta(microseconds=1)
            if issued >= cutoff:
                counts['late_or_unknown_issuance'] += 1
                continue
            if 'enrollment' in data and (user_id not in enrollment or issued < enrollment[user_id]):
                counts['before_enrollment'] += 1
                continue
            if user_id in resets and issued <= resets[user_id]:
                counts['purged_history'] += 1
                continue
            if background_group(background_as_of(data.get('research_background_revisions', []), user_id, issued)) == 'under18':
                counts['ineligible_age'] += 1
                continue
            reviews = [row for row in user_tracking if calendar_date(row['anchor_start_date']) == current['start_date']
                       and row['kind'] != 'no_onset']
            review = max(reviews, key=lambda row: (utc_instant(row['known_at']), int(row['event_id']))) if reviews else None
            label = None
            label_known = None
            if review and review['kind'] in ('missed_tracking', 'true_long_interval'):
                label_known = utc_instant(review['known_at'])
                if label_known <= issued:
                    counts['outcome_already_known'] += 1
                    continue
                label = int(review['kind'] == 'missed_tracking')
            else:
                counts['unreviewed_gaps'] += 1
            snapshot = cycle_rows_as_of(user_events, issued)
            lengths = []
            for previous, next_row in zip(snapshot, snapshot[1:]):
                if next_row['start_date'] > current['start_date']:
                    continue
                past_reviews = [row for row in user_tracking if calendar_date(row['anchor_start_date']) == previous['start_date']
                                and row['kind'] != 'no_onset' and utc_instant(row['known_at']) < issued]
                past = max(past_reviews, key=lambda row: (utc_instant(row['known_at']), int(row['event_id']))) if past_reviews else None
                length = (next_row['start_date'] - previous['start_date']).days
                if 15 <= length <= 45 and (not past or past['kind'] != 'missed_tracking'):
                    lengths.append(length)
            lengths = lengths[-50:]
            median = float(np.median(lengths)) if lengths else np.nan
            iqr = float(np.quantile(lengths, 0.75) - np.quantile(lengths, 0.25)) if len(lengths) >= 2 else np.nan
            gap = (following['start_date'] - current['start_date']).days
            coverage = build_lifestyle_features(data['daily_log_revisions'], user_id=user_id,
                as_of=issued, timezone_name=first['timezone_name'])
            features = {'observed_gap_days': gap, 'history_count': len(lengths), 'personal_median': median,
                'personal_iqr': iqr, 'gap_to_personal_ratio': gap / median if lengths else np.nan,
                'daily_coverage': float(np.mean([coverage[f'{name}_coverage'] for name in ('sleep', 'stress', 'exercise')]))}
            cases.append(TrackingCase(user_id, f'{user_id}/{current["cycle_id"]}/{issued.isoformat()}',
                                      issued, label_known, label, features))
    return sorted(cases, key=lambda case: (case.issued_at, case.key)), counts


def enough(cases):
    labels = [case.label for case in cases]
    return len(cases) >= 20 and len({case.user_id for case in cases}) >= 3 and min(labels.count(0), labels.count(1)) >= 5


def matrix(cases):
    return pd.DataFrame([case.features for case in cases], columns=FEATURES)


def probability_scores(records, *, replicates, seed):
    if not records:
        return {'samples': 0}
    points = np.array([row['point'] for row in records])
    labels = np.array([row['actual'] for row in records])
    baseline = [{**row, 'point': row['baseline']} for row in records]
    brier = float(np.mean((points - labels) ** 2))
    base_brier = float(np.mean([(row['point'] - row['actual']) ** 2 for row in baseline]))
    bins = []
    for index in range(5):
        mask = (points >= index / 5) & ((points < (index + 1) / 5) if index < 4 else (points <= 1))
        bins.append({'lower': index / 5, 'upper': (index + 1) / 5, 'samples': int(mask.sum()),
            'mean_probability': round(float(points[mask].mean()), 4) if mask.any() else None,
            'observed_review_rate': round(float(labels[mask].mean()), 4) if mask.any() else None})
    return {'samples': len(records), 'missed_reviews': int(labels.sum()), 'brier': round(brier, 6),
        'baseline_brier': round(base_brier, 6), 'delta_brier': round(brier - base_brier, 6),
        'delta_brier_ci95': paired_brier_interval(records, baseline, replicates=replicates, seed=seed),
        'reliability_bins': bins}


def run_tracking_evaluation(data, *, calibration_cutoff, test_cutoff, data_as_of, n_splits=3,
                            bootstrap_replicates=1000, seed=42):
    calibration, test, end = (utc_instant(value) for value in (calibration_cutoff, test_cutoff, data_as_of))
    if not calibration < test < end or not 2 <= n_splits <= 10:
        raise ValueError('Invalid tracking research cutoffs')
    cases, exclusions = build_tracking_cases(data, end)
    past, _ = build_tracking_cases(data, calibration)
    middle, _ = build_tracking_cases(data, test)
    train = [c for c in past if c.label is not None and c.issued_at < calibration and c.label_known_at <= calibration]
    cal = [c for c in middle if c.label is not None and calibration <= c.issued_at < test and c.label_known_at <= test]
    targets = [c for c in cases if c.issued_at >= test]
    seen = {c.user_id for c in train}
    folds = [('existing_users', train, cal, [c for c in targets if c.user_id in seen])]
    users = sorted({c.user_id for c in cases})
    if len(users) >= 2:
        for _, indices in GroupKFold(n_splits=min(n_splits, len(users))).split(np.zeros((len(users), 1)), groups=users):
            held = {users[int(index)] for index in indices}
            folds.append(('unseen_users', [c for c in train if c.user_id not in held],
                [c for c in cal if c.user_id not in held], [c for c in targets if c.user_id in held]))
    protocols = {}
    for name in ('existing_users', 'unseen_users'):
        records, fits = [], []
        candidates = reviewed = 0
        for protocol, prefix, calibrators, target in folds:
            if protocol != name:
                continue
            candidates += len(target)
            labelled = [c for c in target if c.label is not None]
            reviewed += len(labelled)
            summary = {'available': enough(prefix), 'training_samples': len(prefix),
                'training_users': len({c.user_id for c in prefix}), 'training_missed': sum(c.label for c in prefix),
                'calibration_samples': len(calibrators), 'probability_calibrated': False,
                'training_labels_available_through': max((c.label_known_at for c in prefix), default=None).isoformat() if prefix else None,
                'calibration_labels_available_through': max((c.label_known_at for c in calibrators), default=None).isoformat() if calibrators else None,
                'held_out_user_overlap': len({c.user_id for c in (*prefix, *calibrators)} & {c.user_id for c in target}) if name == 'unseen_users' else None}
            fits.append(summary)
            if not summary['available'] or not labelled:
                continue
            model = make_pipeline(SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True),
                StandardScaler(), LogisticRegression(C=1, max_iter=1000, solver='liblinear', random_state=42))
            model.fit(matrix(prefix), [c.label for c in prefix])
            probabilities = model.predict_proba(matrix(labelled))[:, 1]
            if enough(calibrators):
                platt = LogisticRegression(C=1, max_iter=1000, solver='liblinear', random_state=42)
                platt.fit(model.decision_function(matrix(calibrators)).reshape(-1, 1), [c.label for c in calibrators])
                probabilities = platt.predict_proba(model.decision_function(matrix(labelled)).reshape(-1, 1))[:, 1]
                summary['probability_calibrated'] = True
            base = (summary['training_missed'] + 1) / (len(prefix) + 2)
            records.extend({'user_id': c.user_id, 'case_key': c.key, 'point': float(p), 'actual': c.label, 'baseline': base}
                           for c, p in zip(labelled, probabilities))
        protocols[name] = {'candidate_samples': candidates, 'reviewed_samples': reviewed,
            'unreviewed_samples': candidates - reviewed, 'skipped_reviewed_samples': reviewed - len(records),
            'fits': fits, 'scores': probability_scores(records, replicates=bootstrap_replicates, seed=seed)}
    return {'version': TRACKING_VERSION, 'parameters': TRACKING_PARAMETERS, 'exclusions': exclusions,
        'target': 'later_user_review_of_closed_gap', 'protocols': protocols,
        'available': any(value['scores']['samples'] for value in protocols.values())}
