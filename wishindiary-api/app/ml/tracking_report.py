"""Whitelist aggregate closed-gap probability diagnostics for administrators."""
import math

from app.features.lifestyle_features import utc_instant
from app.ml.paired_uncertainty import MIN_USERS
from app.ml.tracking_probability import TRACKING_VERSION


def count(value):
    if type(value) is not int or not 0 <= value <= 1_000_000:
        raise ValueError('Invalid tracking count')
    return value


def number(value, lower=0, upper=1):
    if type(value) not in (int, float) or not math.isfinite(value) or not lower <= value <= upper:
        raise ValueError('Invalid tracking probability score')
    return value


def sanitize_tracking_report(raw, calibration, test):
    if raw['version'] != TRACKING_VERSION or raw['target'] != 'later_user_review_of_closed_gap':
        raise ValueError('Unsupported tracking probability contract')
    protocols = {}
    for name in ('existing_users', 'unseen_users'):
        item = raw['protocols'][name]
        result = {key: count(item[key]) for key in ('candidate_samples', 'reviewed_samples', 'unreviewed_samples', 'skipped_reviewed_samples')}
        if result['reviewed_samples'] + result['unreviewed_samples'] != result['candidate_samples']:
            raise ValueError('Tracking cohort denominator differs')
        if len(item['fits']) > 10:
            raise ValueError('Too many tracking fits')
        fits = []
        for fit in item['fits']:
            clean = {key: count(fit[key]) for key in ('training_samples', 'training_users', 'training_missed', 'calibration_samples')}
            if clean['training_missed'] > clean['training_samples'] or clean['training_users'] > clean['training_samples']:
                raise ValueError('Invalid tracking training counts')
            for key, boundary in (('training_labels_available_through', calibration), ('calibration_labels_available_through', test)):
                if fit[key] and utc_instant(fit[key]) > boundary:
                    raise ValueError('Future tracking labels')
            if name == 'unseen_users' and fit['held_out_user_overlap'] != 0:
                raise ValueError('Tracking held-out users leaked')
            clean.update(available=fit['available'] is True, probability_calibrated=fit['probability_calibrated'] is True)
            if clean['available'] and (clean['training_samples'] < 20 or clean['training_users'] < 3
                    or min(clean['training_missed'], clean['training_samples'] - clean['training_missed']) < 5):
                raise ValueError('Sparse tracking model cannot be available')
            if clean['probability_calibrated'] and (not clean['available'] or clean['calibration_samples'] < 20):
                raise ValueError('Sparse probability calibration')
            fits.append(clean)
        score = item['scores']
        cleaned = {'samples': count(score['samples'])}
        if cleaned['samples'] + result['skipped_reviewed_samples'] != result['reviewed_samples']:
            raise ValueError('Tracking evaluated cohort differs')
        if cleaned['samples']:
            cleaned.update(missed_reviews=count(score['missed_reviews']), brier=number(score['brier']),
                baseline_brier=number(score['baseline_brier']), delta_brier=number(score['delta_brier'], -1, 1))
            if cleaned['missed_reviews'] > cleaned['samples'] or abs(cleaned['brier'] - cleaned['baseline_brier'] - cleaned['delta_brier']) > 0.00001:
                raise ValueError('Invalid Brier comparison')
            ci = score['delta_brier_ci95']
            users = count(ci['n_users'])
            if ci['samples'] != cleaned['samples'] or users > cleaned['samples'] or ci['min_users'] != MIN_USERS or ci['level_pct'] != 95:
                raise ValueError('Invalid Brier uncertainty denominator')
            if type(ci['replicates']) is not int or not 200 <= ci['replicates'] <= 10000 or type(ci['seed']) is not int or not 0 <= ci['seed'] < 2**32:
                raise ValueError('Invalid Brier bootstrap')
            interval = {'available': ci['available'] is True, 'n_users': users, 'samples': cleaned['samples'], 'min_users': MIN_USERS}
            if interval['available']:
                interval.update(lower=number(ci['lower'], -1, 1), upper=number(ci['upper'], -1, 1))
                if users < MIN_USERS or interval['lower'] > interval['upper']:
                    raise ValueError('Invalid Brier interval')
            elif users >= MIN_USERS or ci['reason'] != 'too_few_users':
                raise ValueError('Invalid unavailable Brier interval')
            cleaned['delta_brier_ci95'] = interval
            bins = []
            if len(score['reliability_bins']) != 5:
                raise ValueError('Invalid probability bins')
            for index, bucket in enumerate(score['reliability_bins']):
                if bucket['lower'] != index / 5 or bucket['upper'] != (index + 1) / 5:
                    raise ValueError('Probability bin boundaries changed')
                value = {'lower': index / 5, 'upper': (index + 1) / 5, 'samples': count(bucket['samples'])}
                value.update(mean_probability=number(bucket['mean_probability']) if value['samples'] else None,
                    observed_review_rate=number(bucket['observed_review_rate']) if value['samples'] else None)
                bins.append(value)
            if sum(value['samples'] for value in bins) != cleaned['samples']:
                raise ValueError('Probability bins do not partition samples')
            cleaned['reliability_bins'] = bins
        protocols[name] = {**result, 'fits': fits, 'scores': cleaned}
    available = any(value['scores']['samples'] for value in protocols.values())
    if type(raw['available']) is not bool or raw['available'] != bool(available):
        raise ValueError('Invalid tracking report availability')
    return {'available': bool(available), 'version': TRACKING_VERSION, 'protocols': protocols}
