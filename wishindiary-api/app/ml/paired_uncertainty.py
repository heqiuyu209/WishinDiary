"""Paired MAE bootstrap conditional on fitted models, clustering whole users."""
import math

import numpy as np

MIN_USERS = 10
PRIMARY_COMPARISON = {'stage': '0', 'protocol': 'unseen_users',
                      'method': 'sleep_stress_exercise_direct', 'baseline': 'base_direct'}


def paired_mae_interval(candidate, baseline, *, replicates=1000, seed=42):
    if type(replicates) is not int or not 200 <= replicates <= 10_000 or type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError('Invalid bootstrap parameters')
    def indexed(rows):
        result = {}
        for row in rows:
            if row['case_key'] in result:
                raise ValueError('Duplicate paired case')
            if not all(math.isfinite(float(row[key])) for key in ('point', 'actual')):
                raise ValueError('Non-finite paired observation')
            result[row['case_key']] = row
        return result
    left, right = indexed(candidate), indexed(baseline)
    if left.keys() != right.keys():
        raise ValueError('Paired methods must have identical cases')
    clusters = {}
    for key, row in left.items():
        other = right[key]
        if row['user_id'] != other['user_id'] or row['actual'] != other['actual']:
            raise ValueError('Paired user or outcome differs')
        diff = abs(row['point'] - row['actual']) - abs(other['point'] - other['actual'])
        total, count = clusters.get(row['user_id'], (0.0, 0))
        clusters[row['user_id']] = (total + diff, count + 1)
    result = {'available': len(clusters) >= MIN_USERS, 'n_users': len(clusters), 'samples': len(left),
              'min_users': MIN_USERS, 'replicates': replicates, 'seed': seed, 'level_pct': 95}
    if not result['available']:
        return {**result, 'reason': 'too_few_users'}
    sums, counts = np.array([clusters[user] for user in sorted(clusters)], dtype=float).T
    rng = np.random.default_rng(seed)
    draws = np.empty(replicates)
    for index in range(replicates):
        sampled = rng.integers(0, len(clusters), size=len(clusters))
        draws[index] = sums[sampled].sum() / counts[sampled].sum()
    lower, upper = np.quantile(draws, [0.025, 0.975])
    return {**result, 'lower': round(float(lower), 4), 'upper': round(float(upper), 4)}
