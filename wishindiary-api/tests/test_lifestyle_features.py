import math
from datetime import date, datetime, timezone

from app.features.lifestyle_features import build_lifestyle_features

NOW = datetime(2024, 2, 1, 12, tzinfo=timezone.utc)


def revision(n, day, known, **fields):
    return {'revision_id': n, 'user_id': 1, 'log_date': day, 'known_at': known,
            'timezone_name': 'Asia/Shanghai', 'source': 'user_recorded', 'payload': fields}


def features(rows):
    return build_lifestyle_features(rows, user_id=1, as_of=NOW, timezone_name='Asia/Shanghai')


def test_features_ignore_future_edits_backfills_today_and_other_users():
    rows = [revision(1, date(2024, 1, 30), datetime(2024, 1, 31, tzinfo=timezone.utc), sleep_duration_minutes=480)]
    expected = features(rows)
    rows += [revision(2, date(2024, 1, 30), NOW, sleep_duration_minutes=60),
             revision(3, date(2024, 1, 29), datetime(2024, 2, 2, tzinfo=timezone.utc), sleep_duration_minutes=0),
             revision(4, date(2024, 2, 1), datetime(2024, 2, 1, tzinfo=timezone.utc), sleep_duration_minutes=10),
             {**revision(5, date(2024, 1, 31), datetime(2024, 1, 31, tzinfo=timezone.utc), sleep_duration_minutes=0), 'user_id': 2}]
    actual = features(rows)
    assert actual['sleep_mean'] == expected['sleep_mean'] == 480
    assert actual['sleep_coverage'] == 1 / 28
    rows.append(revision(6, date(2024, 1, 30), datetime(2024, 2, 1, 1, tzinfo=timezone.utc), sleep_duration_minutes=300))
    assert features(rows)['sleep_mean'] == 300


def test_unknown_is_not_zero_and_explicit_absence_is_observed():
    assert math.isnan(features([])['exercise_mean'])
    row = revision(1, date(2024, 1, 30), datetime(2024, 1, 31, tzinfo=timezone.utc),
                   is_exercise=False, stress_level=0, sleep_duration_minutes=None)
    result = features([row])
    assert result['exercise_mean'] == result['stress_mean'] == 0
    assert result['exercise_coverage'] == 1 / 28
    assert result['sleep_coverage'] == 0 and math.isnan(result['sleep_mean'])
    assert features([{**row, 'source': 'legacy_unknown'}])['exercise_coverage'] == 0


def test_clock_midpoints_are_circular_and_window_changes_require_both_segments():
    rows = [revision(i, date(2024, 1, d), datetime(2024, 1, d, tzinfo=timezone.utc),
                     sleep_start_minutes=start, sleep_duration_minutes=480,
                     exercise_minutes=minutes, exercise_intensity=2, stress_level=level)
            for i, (d, start, minutes, level) in enumerate([(20, 1380, 20, 1), (30, 0, 60, 3)], 1)]
    result = features(rows)
    assert result['sleep_midpoint_regularity'] > 0.9
    assert result['exercise_change'] == 40 and result['stress_change'] == 2
    assert result['exercise_load_mean'] == 80
