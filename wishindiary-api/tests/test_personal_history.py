from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np
import pandas as pd

from app.ml.personal_history import AdaptiveBlend, ConditionalHistory, history_group, personal_point, variability_group


def case(index, *, values=(26, 26, 26), user=1, actual=26, label_delay=1):
    issued = datetime(2022, 1, 1, tzinfo=timezone.utc) + timedelta(days=index)
    return SimpleNamespace(history=pd.DataFrame({'cycle_length': values}), elapsed=0, actual_remaining=actual,
        issued_at=issued, label_known_at=issued + timedelta(days=label_delay), key=str(index), user_id=user,
        features={f'{group}_coverage': 0.5 for group in ('sleep', 'stress', 'exercise')})


def test_recency_candidates_and_groups_use_only_given_completed_history():
    value = case(0, values=(24,) * 6 + (36,) * 6)
    assert personal_point(value, 'personal_mean') == 30
    assert personal_point(value, 'recent6') == 36
    assert 30 < personal_point(value, 'decay3') < 36
    assert history_group(value) == 'long' and variability_group(value) == 'low'
    assert variability_group(case(0, values=(20, 30, 40))) == 'high'
    value.elapsed = 40
    assert personal_point(value) == 1


def test_gate_never_fits_inner_estimator_on_unavailable_labels_and_learns_from_training_only():
    fitted = []
    class Estimator:
        def fit(self, cases):
            fitted.extend(cases)
            return self
        def predict(self, cases):
            return np.full(len(cases), 40)
    samples = [case(i, user=i % 4, label_delay=30 if i == 50 else 1) for i in range(100)]
    gate = AdaptiveBlend().fit(samples, Estimator)
    cutoff = datetime.fromisoformat(gate.summary['inner_cutoff'])
    assert fitted and all(c.label_known_at < cutoff and c.issued_at < cutoff for c in fitted)
    assert all(c is not samples[50] for c in fitted)
    assert gate.summary['available'] and gate.global_weight == 0
    future = case(1000, values=(26, 26, 26), actual=10000)
    assert gate.predict([future], [40]).tolist() == [26]
    future.actual_remaining = -10000
    assert gate.predict([future], [40]).tolist() == [26]


def test_sparse_gate_uses_fixed_fallback_without_fitting():
    def forbidden():
        raise AssertionError('Sparse validation must not fit an estimator')
    gate = AdaptiveBlend().fit([case(i) for i in range(10)], forbidden)
    assert not gate.summary['available'] and gate.global_weight == 0.5
    assert gate.predict([case(100)], [34]).tolist() == [30]


def test_history_variability_strata_can_learn_different_weights():
    class Estimator:
        def fit(self, cases):
            return self
        def predict(self, cases):
            return np.full(len(cases), 40)
    samples = [case(i, user=i % 4) for i in range(100)]
    for i in range(80, 100):
        samples[i] = case(i, user=i % 4, values=(20, 32, 26), actual=40)
    gate = AdaptiveBlend().fit(samples, Estimator)
    assert gate.weights['short/low/covered'] == 0
    assert gate.weights['short/high/covered'] == 1
    assert gate.summary['learned_groups'] == 2
    assert gate.predict([case(200), case(201, values=(20, 32, 26))], [40, 40]).tolist() == [26, 40]


def test_conditional_waiting_uses_survival_mass_and_no_future_outcome():
    model = ConditionalHistory().fit([case(i, user=i % 3, actual=26) for i in range(10)])
    target = case(100, values=(20, 20, 20, 20, 30, 30), actual=10000)
    initial = model.predict([target])[0]
    target.elapsed = 21
    updated = model.predict([target])[0]
    assert updated > max(1, initial - 21)
    target.actual_remaining = -10000
    assert model.predict([target])[0] == updated
    assert abs(model.population.sum() - 1) < 1e-12
