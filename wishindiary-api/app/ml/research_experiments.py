"""Immutable local experiment plans, private snapshots, replay and safe registry."""
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
import re
from uuid import uuid4

from app.core.config import settings
from app.features.lifestyle_features import LIFESTYLE_FEATURE_VERSION, utc_instant
from app.ml.lifestyle_report import lifestyle_pipeline_fingerprint
from app.ml.paired_uncertainty import PRIMARY_COMPARISON
from app.ml.lifestyle_evaluation import PARAMETERS
from app.services.research_dataset_service import (
    authorization_is_current, fingerprint, read_authorized_database, report_authorization, validate_snapshot,
)


def experiment_root():
    return settings.model_abs_path.parent / 'research_experiments'


def run_directory(run_id):
    if not re.fullmatch(r'[a-f0-9]{32}', run_id):
        raise ValueError('Invalid experiment ID')
    root = experiment_root()
    path = root / run_id
    if root.is_symlink() or path.is_symlink():
        raise ValueError('Experiment directories cannot be symlinks')
    return path


def read_json(path, max_bytes=1_000_000):
    if path.is_symlink() or path.stat().st_size > max_bytes:
        raise ValueError('Invalid or oversized experiment artifact')
    return json.loads(path.read_text(encoding='utf-8'))


def write_exclusive(path, value):
    payload = json.dumps(value, sort_keys=True, default=str, ensure_ascii=False, indent=2, allow_nan=False)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8') as file:
        file.write(payload)


def plan_signature(sha256):
    return hmac.new(settings.SECRET_KEY.encode(), f'research-plan-v1/{sha256}'.encode(), hashlib.sha256).hexdigest()


def register_protocol(*, calibration_cutoff, test_cutoff, data_as_of, bootstrap_replicates=1000, synthetic_users=12):
    from scripts.train import _collect_env_metadata
    calibration, test, end = (utc_instant(value) for value in (calibration_cutoff, test_cutoff, data_as_of))
    if not calibration < test < end or type(bootstrap_replicates) is not int or not 200 <= bootstrap_replicates <= 10000:
        raise ValueError('Invalid chronological protocol or bootstrap count')
    if type(synthetic_users) is not int or not 3 <= synthetic_users <= 100:
        raise ValueError('Synthetic demonstration requires 3–100 users')
    now = datetime.now(timezone.utc)
    run_id = uuid4().hex
    protocol = {'schema_version': 1, 'run_id': run_id, 'registered_at': now.isoformat(),
        'kind': 'prospective_plan' if now < test else 'retrospective_exploration',
        'calibration_cutoff': calibration.isoformat(), 'test_cutoff': test.isoformat(), 'data_as_of': end.isoformat(),
        'feature_version': LIFESTYLE_FEATURE_VERSION, 'pipeline_sha256': lifestyle_pipeline_fingerprint(),
        'primary_comparison': PRIMARY_COMPARISON, 'bootstrap_replicates': bootstrap_replicates,
        'bootstrap_seed': 42, 'rf_seed': 42, 'n_splits': 3, 'target_coverage': 0.9,
        'rf_parameters': dict(PARAMETERS),
        'synthetic_users': synthetic_users, 'synthetic_cycles': 22, 'environment': _collect_env_metadata()}
    path = run_directory(run_id)
    if path.parent.exists() and sum(1 for _ in path.parent.iterdir()) >= 1000:
        raise ValueError('Local experiment registry is full; archive completed runs privately')
    path.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.chmod(path.parent, 0o700)
    digest = fingerprint(protocol)
    write_exclusive(path / 'protocol.json', {'protocol': protocol, 'sha256': digest, 'signature': plan_signature(digest)})
    return run_id


def read_protocol(run_id, *, require_environment=False):
    envelope = read_json(run_directory(run_id) / 'protocol.json')
    protocol, digest = envelope['protocol'], envelope['sha256']
    if fingerprint(protocol) != digest or not hmac.compare_digest(envelope['signature'], plan_signature(digest)):
        raise ValueError('Registered protocol changed')
    if protocol['run_id'] != run_id or protocol['schema_version'] != 1 or protocol['primary_comparison'] != PRIMARY_COMPARISON:
        raise ValueError('Unsupported registered protocol')
    if require_environment:
        from scripts.train import _collect_env_metadata
        if protocol['pipeline_sha256'] != lifestyle_pipeline_fingerprint():
            raise ValueError('Pipeline changed; register a new protocol')
        if protocol['environment']['dependencies'] != _collect_env_metadata()['dependencies']:
            raise ValueError('Dependency versions changed; restore the registered environment or register a new plan')
        if protocol['rf_parameters'] != PARAMETERS:
            raise ValueError('Estimator parameters changed; register a new plan')
    return protocol, digest


def freeze_dataset(run_id, *, synthetic_only=False):
    from scripts.lifestyle_backtest import synthetic_event_data
    protocol, _ = read_protocol(run_id, require_environment=True)
    if utc_instant(protocol['data_as_of']) > datetime.now(timezone.utc):
        raise ValueError('Planned observation cutoff has not been reached')
    if synthetic_only:
        data = synthetic_event_data(protocol['synthetic_users'], protocol['synthetic_cycles'])
        snapshot = {'schema_version': 1, 'source': 'synthetic', 'data': data, 'dataset_sha256': fingerprint(data)}
    else:
        snapshot = {**read_authorized_database(), 'source': 'authorized_database'}
    write_exclusive(run_directory(run_id) / 'dataset_snapshot.json', snapshot)
    return snapshot['dataset_sha256']


def read_dataset(run_id, protocol):
    from scripts.lifestyle_backtest import synthetic_event_data
    snapshot = read_json(run_directory(run_id) / 'dataset_snapshot.json', 100_000_000)
    if fingerprint(snapshot['data']) != snapshot['dataset_sha256']:
        raise ValueError('Frozen dataset changed')
    if snapshot['source'] == 'synthetic':
        expected = synthetic_event_data(protocol['synthetic_users'], protocol['synthetic_cycles'])
        if snapshot['dataset_sha256'] != fingerprint(expected):
            raise ValueError('Synthetic snapshot does not match the registered fixture')
        return snapshot['data'], 'synthetic', None
    if snapshot['source'] != 'authorized_database':
        raise ValueError('Unsupported snapshot source')
    return validate_snapshot(snapshot), 'authorized_database', report_authorization(snapshot)


def manifest_for(path, report, protocol_sha256):
    return {'schema_version': 1, 'protocol_sha256': protocol_sha256,
            'evaluation_sha256': fingerprint(report['evaluation']),
            'files': {name: hashlib.sha256((path / name).read_bytes()).hexdigest()
                      for name in ('protocol.json', 'dataset_snapshot.json', 'report.json')}}


def verify_manifest(path, *, include_snapshot=True):
    manifest = read_json(path / 'manifest.json')
    if manifest['schema_version'] != 1 or set(manifest['files']) != {'protocol.json', 'dataset_snapshot.json', 'report.json'}:
        raise ValueError('Invalid experiment manifest')
    for name, digest in manifest['files'].items():
        artifact = path / name
        maximum = 100_000_000 if name == 'dataset_snapshot.json' else 1_000_000
        if artifact.is_symlink() or not artifact.is_file() or artifact.stat().st_size > maximum:
            raise ValueError('Invalid experiment artifact')
        if not include_snapshot and name == 'dataset_snapshot.json':
            continue
        if hashlib.sha256(artifact.read_bytes()).hexdigest() != digest:
            raise ValueError('Experiment artifact changed')
    return manifest


def execute_experiment(run_id, *, replay=False, publish_report=False):
    from scripts.lifestyle_backtest import evaluate_data
    path = run_directory(run_id)
    protocol, protocol_sha256 = read_protocol(run_id, require_environment=True)
    if replay:
        manifest = verify_manifest(path)
        if manifest['protocol_sha256'] != protocol_sha256:
            raise ValueError('Experiment protocol manifest differs')
    elif (path / 'report.json').exists() or (path / 'manifest.json').exists():
        raise ValueError('Run already has a result; use replay or register a new plan')
    data, source, authorization = read_dataset(run_id, protocol)
    report = evaluate_data(data, source, calibration_cutoff=protocol['calibration_cutoff'],
        test_cutoff=protocol['test_cutoff'], data_as_of=protocol['data_as_of'], authorization=authorization,
        bootstrap_replicates=protocol['bootstrap_replicates'])
    report['experiment'] = {'run_id': run_id, 'protocol_sha256': protocol_sha256,
                            'registered_at': protocol['registered_at'], 'kind': protocol['kind']}
    if replay:
        if fingerprint(report['evaluation']) != manifest['evaluation_sha256']:
            raise ValueError('Replay differs from the frozen evaluation')
    else:
        write_exclusive(path / 'report.json', report)
        write_exclusive(path / 'manifest.json', manifest_for(path, report, protocol_sha256))
    if publish_report:
        if authorization and not authorization_is_current(authorization):
            raise ValueError('Consent changed before publishing the aggregate report')
        destination = settings.model_abs_path.parent / 'lifestyle_evaluation_report.json'
        temporary = destination.with_name(f'.{run_id}.report.tmp')
        write_exclusive(temporary, report)
        temporary.replace(destination)
    return {'run_id': run_id, 'replayed': replay, 'eligible_cases': report['evaluation']['eligible_cases']}


def list_experiments():
    root = experiment_root()
    if not root.exists():
        return []
    if root.is_symlink():
        return []
    # No user-controlled path or artifact content is exposed through the API.
    paths = [path for path in root.iterdir() if re.fullmatch(r'[a-f0-9]{32}', path.name) and path.is_dir() and not path.is_symlink()]
    entries = []
    for path in sorted(paths, key=lambda item: item.stat().st_mtime, reverse=True)[:20]:
        try:
            protocol, digest = read_protocol(path.name)
            entry = {'run_id': path.name, 'registered_at': protocol['registered_at'], 'kind': protocol['kind'],
                     'calibration_cutoff': protocol['calibration_cutoff'], 'test_cutoff': protocol['test_cutoff'],
                     'data_as_of': protocol['data_as_of'], 'protocol_sha256': digest,
                     'pipeline_matches': protocol['pipeline_sha256'] == lifestyle_pipeline_fingerprint(),
                     'status': 'registered'}
            if (path / 'report.json').exists():
                manifest = verify_manifest(path, include_snapshot=False)
                if manifest['protocol_sha256'] != digest:
                    raise ValueError('Protocol mismatch')
                report = read_json(path / 'report.json')
                if report['dataset']['source'] != 'synthetic' and not authorization_is_current(report.get('authorization')):
                    entry['status'] = 'authorization_changed'
                else:
                    entry.update(status='complete', source=report['dataset']['source'],
                                 n_users=report['dataset']['n_users'], eligible_cases=report['evaluation']['eligible_cases'])
            elif (path / 'dataset_snapshot.json').exists():
                entry['status'] = 'frozen'
            entries.append(entry)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            entries.append({'run_id': path.name, 'status': 'invalid'})
    return entries
