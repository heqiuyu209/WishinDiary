"""Offline personal-history candidates and a temporally trained blend gate."""
import numpy as np

PERSONALIZATION_PARAMETERS = {
    'recent_window': 6, 'decay_half_life_cycles': 3, 'volatility_window': 6,
    'volatility_threshold_days': 2, 'inner_train_fraction': 0.6,
    'weight_grid': [0, 0.25, 0.5, 0.75, 1],
    'min_gate_samples': 20, 'min_gate_users': 3, 'fallback_model_weight': 0.5,
}
PERSONAL_METHODS = ('personal_mean', 'recent6', 'decay3')
CONDITIONAL_PARAMETERS = {'support_days': [15, 45], 'population_pseudocount': 0.5, 'history_k': 4}


def history_group(case):
    size = len(case.history)
    return 'short' if size < 6 else 'medium' if size < 12 else 'long'


def variability_group(case):
    values = case.history.cycle_length.to_numpy(dtype=float)[-6:]
    return 'low' if np.std(values, ddof=1) <= 2 else 'high'


def coverage_group(case):
    coverage = np.mean([case.features[f'{name}_coverage'] for name in ('sleep', 'stress', 'exercise')])
    return 'none' if coverage == 0 else 'sparse' if coverage < 0.5 else 'covered'


def gate_group(case):
    return '/'.join((history_group(case), variability_group(case), coverage_group(case)))


def personal_point(case, method='decay3', *, rounded=True):
    values = case.history.cycle_length.to_numpy(dtype=float)
    if method == 'personal_mean':
        value = np.mean(values)
    elif method == 'recent6':
        value = np.mean(values[-6:])
    elif method == 'decay3':
        weights = 2 ** (-np.arange(len(values) - 1, -1, -1) / 3)
        value = np.average(values, weights=weights)
    else:
        raise ValueError('Unknown personal history method')
    remaining = float(value) - case.elapsed
    return max(1, round(remaining) if rounded else remaining)


class AdaptiveBlend:
    """Learn weights on a later *training* segment, never calibration/test.

    The inner RF only sees labels available before its issuance boundary.
    Its validation labels choose a finite weight grid; sparse strata use the
    global learned weight, and sparse global data use a documented fixed 0.5.
    """
    def fit(self, cases, estimator_factory):
        ordered = sorted(cases, key=lambda case: (case.issued_at, case.key))
        boundary = ordered[min(int(len(ordered) * 0.6), len(ordered) - 1)].issued_at
        prefix = [case for case in ordered if case.issued_at < boundary and case.label_known_at < boundary]
        validation = [case for case in ordered if case.issued_at >= boundary]
        self.weights = {}
        self.global_weight = 0.5
        self.summary = {
            'available': False, 'reason': 'insufficient_training_validation',
            'inner_cutoff': boundary.isoformat(), 'training_samples': len(prefix),
            'validation_samples': len(validation), 'validation_users': len({c.user_id for c in validation}),
            'training_labels_available_through': max((c.label_known_at for c in prefix), default=None).isoformat() if prefix else None,
            'validation_labels_available_through': max((c.label_known_at for c in validation), default=None).isoformat() if validation else None,
            'global_model_weight': self.global_weight, 'learned_groups': 0,
        }
        if not prefix or len(validation) < 20 or self.summary['validation_users'] < 3:
            return self
        predictions = estimator_factory().fit(prefix).predict(validation)
        personal = np.array([personal_point(case, rounded=False) for case in validation])
        actual = np.array([case.actual_remaining for case in validation])
        def select(indices):
            # Ties favor less reliance on the RF; this choice is frozen.
            losses = [np.mean(np.abs(np.maximum(1, np.rint(weight * predictions[indices]
                + (1 - weight) * personal[indices])) - actual[indices]))
                for weight in PERSONALIZATION_PARAMETERS['weight_grid']]
            return PERSONALIZATION_PARAMETERS['weight_grid'][int(np.argmin(losses))]
        self.global_weight = select(np.arange(len(validation)))
        for group in sorted({gate_group(case) for case in validation}):
            indices = [i for i, case in enumerate(validation) if gate_group(case) == group]
            if len(indices) >= 20 and len({validation[i].user_id for i in indices}) >= 3:
                self.weights[group] = select(indices)
        self.summary.update(available=True, reason=None, global_model_weight=self.global_weight,
                            learned_groups=len(self.weights))
        return self

    def predict(self, cases, model_points):
        weights = np.array([self.weights.get(gate_group(case), self.global_weight) for case in cases])
        personal = np.array([personal_point(case, rounded=False) for case in cases])
        return np.maximum(1, np.rint(weights * np.asarray(model_points) + (1 - weights) * personal))


class ConditionalHistory:
    """Smoothed empirical waiting distribution; positive stages need no-onset evidence.

    Population labels come from the training prefix only and users have equal
    total mass. Personal completed history is available at issuance. Conditioning
    is only applied to the explicit-confirmation cohort built by the evaluator.
    """
    def fit(self, cases):
        self.support = np.arange(15, 46)
        mass = np.full(len(self.support), 0.5)
        for user_id in sorted({case.user_id for case in cases}):
            values = [round(case.actual_remaining + case.elapsed) for case in cases if case.user_id == user_id]
            counts = np.array([values.count(day) for day in self.support], dtype=float)
            if counts.sum():
                mass += counts / counts.sum()
        self.population = mass / mass.sum()
        return self

    def predict(self, cases):
        points = []
        for case in cases:
            values = case.history.cycle_length.to_numpy(dtype=int)
            counts = np.array([np.sum(values == day) for day in self.support], dtype=float)
            weight = len(values) / (len(values) + 4)
            personal = counts / counts.sum() if counts.sum() else self.population
            mass = weight * personal + (1 - weight) * self.population
            eligible = self.support > case.elapsed
            if not eligible.any():
                raise ValueError('Waiting day exceeds the conditional research support')
            remaining = np.average(self.support[eligible] - case.elapsed, weights=mass[eligible])
            points.append(max(1, round(float(remaining))))
        return np.array(points)
