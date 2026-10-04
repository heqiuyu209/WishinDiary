"""Bounded, aggregate-only research report reader."""
import hashlib
import json
import logging
import math
from pathlib import Path

from app.core.config import settings
from app.features.lifestyle_features import FEATURE_GROUPS, LIFESTYLE_FEATURE_VERSION, utc_instant
from app.services.research_dataset_service import authorization_is_current
from app.ml.paired_uncertainty import MIN_USERS, PRIMARY_COMPARISON
from app.ml.personal_history import PERSONAL_METHODS
from app.ml.tracking_report import sanitize_tracking_report

logger = logging.getLogger(__name__)
METHODS = tuple(group + suffix for group in FEATURE_GROUPS for suffix in ('_direct', '_shrinkage', '_adaptive')) + ('mean3', 'median3', 'ewma', *PERSONAL_METHODS, 'conditional_history')


def lifestyle_pipeline_fingerprint():
    root = Path(__file__).resolve().parents[1]
    paths = ('ml/lifestyle_evaluation.py', 'features/lifestyle_features.py',
             'features/cycle_feature_engineering.py', 'ml/contract.py', 'ml/prediction_scope.py',
             'features/research_background.py', 'core/research_policy.py', 'ml/paired_uncertainty.py',
             'services/research_dataset_service.py', '../scripts/lifestyle_backtest.py', 'ml/research_experiments.py',
             'ml/personal_history.py', 'ml/tracking_probability.py')
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.encode() + b'\0' + (root / path).read_bytes() + b'\0')
    return digest.hexdigest()


def count(value):
    if type(value) is not int or not 0 <= value <= 1_000_000:
        raise ValueError('Invalid research count')
    return value


def score(raw):
    result = {'samples': count(raw['samples'])}
    if not result['samples']:
        return result
    for key in ('mae', 'hit_rate_within_2d', 'coverage_pct', 'mean_width_days', 'delta_mae_vs_base'):
        if key in raw:
            value = raw[key]
            if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 10000:
                raise ValueError('Invalid research score')
            if key != 'delta_mae_vs_base' and value < 0:
                raise ValueError('Negative research score')
            if key.endswith('pct') or key == 'hit_rate_within_2d':
                if value > 100:
                    raise ValueError('Invalid research percentage')
            result[key] = value
    for key in ('mae', 'hit_rate_within_2d'):
        if key not in result:
            raise ValueError('Missing point score')
    result.update(interval_samples=count(raw['interval_samples']),
                  interval_unavailable_samples=count(raw['interval_unavailable_samples']))
    if result['interval_samples'] + result['interval_unavailable_samples'] != result['samples']:
        raise ValueError('Invalid interval denominator')
    if result['interval_samples'] and not {'coverage_pct', 'mean_width_days'} <= result.keys():
        raise ValueError('Missing interval scores')
    if 'delta_mae_ci95' in raw:
        ci = raw['delta_mae_ci95']
        n_users = count(ci['n_users'])
        if ci['samples'] != result['samples'] or n_users > result['samples'] or ci['min_users'] != MIN_USERS or ci['level_pct'] != 95:
            raise ValueError('Invalid paired uncertainty denominator')
        if type(ci['replicates']) is not int or not 200 <= ci['replicates'] <= 10_000 or type(ci['seed']) is not int or not 0 <= ci['seed'] < 2**32:
            raise ValueError('Invalid paired uncertainty parameters')
        clean = {'available': ci['available'] is True, 'n_users': n_users, 'samples': result['samples'], 'min_users': MIN_USERS}
        if clean['available']:
            lower, upper = ci['lower'], ci['upper']
            if n_users < MIN_USERS or any(type(v) not in (float, int) or not math.isfinite(v) or abs(v) > 10000 for v in (lower, upper)) or lower > upper:
                raise ValueError('Invalid paired uncertainty range')
            clean.update(lower=lower, upper=upper)
        elif n_users >= MIN_USERS or ci['reason'] != 'too_few_users':
            raise ValueError('Invalid unavailable uncertainty')
        result['delta_mae_ci95'] = clean
    return result


def read_lifestyle_report():
    path = settings.model_abs_path.parent / 'lifestyle_evaluation_report.json'
    if not path.is_file():
        return {'available': False, 'message': '尚未生成生活因素离线对照报告'}
    try:
        if path.stat().st_size > 1_000_000:
            raise ValueError('Oversized research report')
        raw = json.loads(path.read_text(encoding='utf-8'))
        evaluation = raw['evaluation']
        if raw['schema_version'] != 1 or evaluation['feature_version'] != LIFESTYLE_FEATURE_VERSION:
            raise ValueError('Unsupported research contract')
        calibration, test = utc_instant(evaluation['calibration_cutoff']), utc_instant(evaluation['test_cutoff'])
        if utc_instant(evaluation['data_as_of']) <= test:
            raise ValueError('Invalid data observation cutoff')
        if calibration >= test or not 0 < evaluation['target_coverage_pct'] < 100:
            raise ValueError('Invalid cutoffs or target')
        source = raw['dataset']['source']
        if source not in ('synthetic', 'authorized_event_json', 'authorized_database'):
            raise ValueError('Unknown provenance')
        if source != 'synthetic' and not authorization_is_current(raw.get('authorization')):
            return {'available': False, 'message': '研究授权已变化或快照未验证，请重新生成授权数据快照与报告'}
        stages = {}
        for stage in ('0', '7', '14', '21'):
            item = evaluation['stages'][stage]
            protocols = {}
            for name in ('existing_users', 'unseen_users'):
                result = item['protocols'][name]
                samples = count(result['samples'])
                metrics = {method: score(result['metrics'][method]) for method in METHODS if method in result['metrics']}
                if samples and (set(metrics) != set(METHODS) or any(value['samples'] != samples for value in metrics.values())):
                    raise ValueError('Methods do not share the test cohort')
                fits = []
                if len(result['fits']) > 10:
                    raise ValueError('Too many fits')
                for fit in result['fits']:
                    if utc_instant(fit['training_labels_available_through']) > calibration:
                        raise ValueError('Future training labels')
                    if fit['calibration_labels_available_through'] and utc_instant(fit['calibration_labels_available_through']) > test:
                        raise ValueError('Future calibration labels')
                    if name == 'unseen_users' and fit['held_out_user_overlap'] != 0:
                        raise ValueError('Held-out users leaked into training')
                    clean_fit = {'training_samples': count(fit['training_samples']), 'calibration_samples': count(fit['calibration_samples'])}
                    if 'adaptive_blend' in fit:
                        gates = {}
                        for group in FEATURE_GROUPS:
                            gate = fit['adaptive_blend'][group]
                            boundary = utc_instant(gate['inner_cutoff'])
                            if boundary >= calibration or (gate['training_labels_available_through'] and utc_instant(gate['training_labels_available_through']) >= boundary):
                                raise ValueError('Future inner training labels')
                            if gate['validation_labels_available_through'] and utc_instant(gate['validation_labels_available_through']) > calibration:
                                raise ValueError('Future gate validation labels')
                            weight = gate['global_model_weight']
                            if type(weight) not in (int, float) or weight not in (0, 0.25, 0.5, 0.75, 1):
                                raise ValueError('Invalid blend weight')
                            validation_samples, validation_users = count(gate['validation_samples']), count(gate['validation_users'])
                            trained, strata = count(gate['training_samples']), count(gate['learned_groups'])
                            if validation_users > validation_samples or trained + validation_samples > clean_fit['training_samples'] or strata > 18:
                                raise ValueError('Invalid blend gate counts')
                            if gate['available'] is True and (not trained or validation_samples < 20 or validation_users < 3):
                                raise ValueError('Sparse blend gate cannot be available')
                            if gate['available'] is not True and (weight != 0.5 or strata):
                                raise ValueError('Invalid blend fallback')
                            gates[group] = {'available': gate['available'] is True,
                                'training_samples': count(gate['training_samples']), 'validation_samples': count(gate['validation_samples']),
                                'validation_users': count(gate['validation_users']), 'learned_groups': count(gate['learned_groups']),
                                'global_model_weight': weight}
                        clean_fit['adaptive_blend'] = gates
                    fits.append(clean_fit)
                groups = {group: {method: score(values[method]) for method in METHODS if method in values}
                          for group, values in result['coverage_groups'].items() if group in ('none', 'sparse', 'covered')}
                for method in metrics:
                    if sum(group[method]['samples'] for group in groups.values()) != samples:
                        raise ValueError('Coverage groups do not partition samples')
                candidate = count(result['candidate_samples'])
                if candidate < samples:
                    raise ValueError('Invalid candidate denominator')
                protocols[name] = {'samples': samples, 'candidate_samples': candidate,
                    'skipped_empty_folds': count(result['skipped_empty_folds']),
                    'excluded_unseen_cases': count(result['excluded_unseen_cases']), 'fits': fits,
                    'metrics': metrics, 'coverage_groups': groups}
                if 'background_groups' in result:
                    backgrounds = {group: {method: score(values[method]) for method in METHODS if method in values}
                                   for group, values in result['background_groups'].items()
                                   if group in ('unknown', 'explicit_none', 'reported_context')}
                    for method in metrics:
                        if sum(group[method]['samples'] for group in backgrounds.values()) != samples:
                            raise ValueError('Background groups do not partition samples')
                    protocols[name]['background_groups'] = backgrounds
                for key, names in (('history_groups', ('short', 'medium', 'long')), ('variability_groups', ('low', 'high'))):
                    if key in result:
                        partition = {group: {method: score(result[key][group][method]) for method in metrics} for group in names}
                        if any(sum(values[method]['samples'] for values in partition.values()) != samples for method in metrics):
                            raise ValueError('Personal history groups do not partition samples')
                        protocols[name][key] = partition
            stages[stage] = {'target': 'cycle_length_days' if stage == '0' else 'remaining_wait_days', 'protocols': protocols}
        metadata = raw.get('metadata', {})
        tracking = sanitize_tracking_report(evaluation['tracking_probability'], calibration, test) if 'tracking_probability' in evaluation else None
        return {'available': True, 'feature_version': LIFESTYLE_FEATURE_VERSION,
            'pipeline_matches_report': raw['pipeline_sha256'] == lifestyle_pipeline_fingerprint(),
            'generated_at': str(metadata.get('generated_at', ''))[:40], 'git_commit': str(metadata.get('git_commit', ''))[:40],
            'dataset': {'source': source, 'n_users': count(raw['dataset']['n_users'])},
            'calibration_cutoff': evaluation['calibration_cutoff'], 'test_cutoff': evaluation['test_cutoff'],
            'data_as_of': evaluation['data_as_of'],
            'target_coverage_pct': evaluation['target_coverage_pct'], 'eligible_cases': count(evaluation['eligible_cases']),
            'exclusions': {key: count(value) for key, value in evaluation['exclusions'].items() if key in (
                'candidate_intervals', 'late_or_unknown_issuance', 'edited_anchor', 'purged_history', 'unsupported_history',
                'missing_history', 'confirmed_missed', 'dynamic_without_timely_confirmation', 'before_enrollment', 'ineligible_age')},
            'primary_comparison': PRIMARY_COMPARISON if evaluation.get('primary_comparison') == PRIMARY_COMPARISON else None,
            'tracking_probability': tracking, 'stages': stages}
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        logger.warning('Lifestyle report invalid; regenerate the aggregate report')
        return {'available': False, 'message': '生活因素报告无效，请重新生成'}
