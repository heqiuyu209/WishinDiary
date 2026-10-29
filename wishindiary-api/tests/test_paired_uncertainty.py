import pytest

from app.ml.paired_uncertainty import paired_mae_interval


def pairs(n_users=12):
    baseline, candidate = [], []
    for user in range(n_users):
        for case in range(1 + user % 3):
            row = {'user_id': user, 'case_key': f'{user}/{case}', 'actual': 30.0, 'point': 32.0}
            baseline.append(row)
            candidate.append({**row, 'point': 31.0})
    return candidate, baseline


def test_cluster_bootstrap_preserves_pairing_and_is_reproducible():
    left, right = pairs()
    result = paired_mae_interval(left, right)
    assert result == paired_mae_interval(left[::-1], right[::-1])
    assert result['available'] and result['n_users'] == 12 and result['lower'] == result['upper'] == -1
    # One prolific user is still one cluster, not 100 independent subjects.
    left, right = pairs(1)
    for index in range(100):
        right.append({**right[0], 'case_key': f'extra/{index}'})
        left.append({**left[0], 'case_key': f'extra/{index}'})
    result = paired_mae_interval(left, right)
    assert result['n_users'] == 1 and not result['available'] and 'lower' not in result


def test_bootstrap_rejects_mismatched_or_duplicate_cases_and_wrong_outcome():
    left, right = pairs()
    with pytest.raises(ValueError, match='identical cases'):
        paired_mae_interval(left[:-1], right)
    with pytest.raises(ValueError, match='Duplicate'):
        paired_mae_interval(left + [left[0]], right)
    right[0]['actual'] = 31
    with pytest.raises(ValueError, match='outcome differs'):
        paired_mae_interval(left, right)
