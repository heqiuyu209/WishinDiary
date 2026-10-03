"""Shared candidate features for training, inference and as-of backtests."""
import json
import math
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np

from app.features.cycle_feature_engineering import build_prediction_feature_row
from app.ml.contract import FEATURE_NAMES

LIFESTYLE_FEATURE_VERSION = "cycle-lifestyle-research-v1"
SLEEP_NAMES = ("sleep_mean", "sleep_std", "sleep_coverage", "sleep_quality_mean",
               "sleep_midpoint_sin", "sleep_midpoint_cos", "sleep_midpoint_regularity",
               "sleep_time_coverage", "late_night_rate", "night_shift_rate")
STRESS_NAMES = ("stress_mean", "stress_max", "stress_coverage", "stress_change")
EXERCISE_NAMES = ("exercise_mean", "exercise_coverage", "exercise_intensity_mean", "exercise_load_mean", "exercise_change")
FEATURE_GROUPS = {
    "base": (*FEATURE_NAMES, "elapsed_days"),
    "sleep": (*FEATURE_NAMES, "elapsed_days", *SLEEP_NAMES),
    "sleep_stress": (*FEATURE_NAMES, "elapsed_days", *SLEEP_NAMES, *STRESS_NAMES),
    "sleep_stress_exercise": (*FEATURE_NAMES, "elapsed_days", *SLEEP_NAMES, *STRESS_NAMES, *EXERCISE_NAMES),
}
WINDOW_DAYS = 28


def utc_instant(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if not isinstance(value, datetime):
        raise ValueError("Event time must be a datetime")
    # Database DATETIME(6) event columns are explicitly UTC. CSV uses ISO UTC.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def daily_rows_as_of(revisions, *, user_id, as_of, timezone_name):
    if as_of.tzinfo is None:
        raise ValueError("Prediction time must be timezone-aware")
    cutoff = utc_instant(as_of)
    day = cutoff.astimezone(ZoneInfo(timezone_name)).date()
    selected = {}
    for row in revisions:
        if int(row['user_id']) != user_id or row['source'] != 'user_recorded':
            continue
        known = utc_instant(row['known_at'])
        log_day = row['log_date']
        if isinstance(log_day, str):
            log_day = datetime.fromisoformat(log_day).date()
        if not day - timedelta(days=WINDOW_DAYS) <= log_day < day or known >= cutoff:
            continue
        rank = (known, int(row['revision_id']))
        if log_day not in selected or rank > selected[log_day][0]:
            payload = json.loads(row['payload']) if isinstance(row['payload'], str) else row['payload']
            selected[log_day] = (rank, payload)
    return [(log_day, item[1]) for log_day, item in sorted(selected.items())]


def build_lifestyle_features(revisions, *, user_id, as_of, timezone_name):
    rows = daily_rows_as_of(revisions, user_id=user_id, as_of=as_of, timezone_name=timezone_name)
    day = as_of.astimezone(ZoneInfo(timezone_name)).date()
    def observed(key):
        return [(d, float(row[key])) for d, row in rows if row.get(key) is not None]
    def mean(values):
        return float(np.mean(values)) if values else math.nan
    def change(values):
        current = [v for d, v in values if day - timedelta(days=7) <= d < day]
        previous = [v for d, v in values if day - timedelta(days=14) <= d < day - timedelta(days=7)]
        return mean(current) - mean(previous) if current and previous else math.nan
    sleep = observed('sleep_duration_minutes')
    stress = observed('stress_level')
    exercise = []
    intensities, loads, midpoints = [], [], []
    for d, row in rows:
        duration = 0 if row.get('is_exercise') is False else row.get('exercise_minutes')
        intensity = 0 if row.get('is_exercise') is False else row.get('exercise_intensity')
        if duration is not None:
            exercise.append((d, float(duration)))
        if intensity is not None:
            intensities.append(float(intensity))
        if duration is not None and intensity is not None:
            loads.append(float(duration) * float(intensity))
        if row.get('sleep_start_minutes') is not None and row.get('sleep_duration_minutes') is not None:
            midpoints.append((float(row['sleep_start_minutes']) + float(row['sleep_duration_minutes']) / 2) % 1440)
    angles = np.array(midpoints) * 2 * np.pi / 1440
    sin, cos = (float(np.sin(angles).mean()), float(np.cos(angles).mean())) if midpoints else (math.nan, math.nan)
    return {
        'sleep_mean': mean([v for _, v in sleep]),
        'sleep_std': float(np.std([v for _, v in sleep])) if len(sleep) >= 2 else math.nan,
        'sleep_coverage': len(sleep) / WINDOW_DAYS,
        'sleep_quality_mean': mean([v for _, v in observed('sleep_quality')]),
        'sleep_midpoint_sin': sin, 'sleep_midpoint_cos': cos,
        'sleep_midpoint_regularity': math.hypot(sin, cos) if len(midpoints) >= 2 else math.nan,
        'sleep_time_coverage': len(midpoints) / WINDOW_DAYS,
        'late_night_rate': mean([v for _, v in observed('is_late_night')]),
        'night_shift_rate': mean([v for _, v in observed('is_night_shift')]),
        'stress_mean': mean([v for _, v in stress]), 'stress_max': max([v for _, v in stress], default=math.nan),
        'stress_coverage': len(stress) / WINDOW_DAYS, 'stress_change': change(stress),
        'exercise_mean': mean([v for _, v in exercise]), 'exercise_coverage': len(exercise) / WINDOW_DAYS,
        'exercise_intensity_mean': mean(intensities), 'exercise_load_mean': mean(loads),
        'exercise_change': change(exercise),
    }


def build_research_feature_row(history, revisions, *, user_id, anchor, as_of, timezone_name, elapsed_days=0):
    return {**build_prediction_feature_row(history, anchor), 'elapsed_days': float(elapsed_days),
            **build_lifestyle_features(revisions, user_id=user_id, as_of=as_of, timezone_name=timezone_name)}
