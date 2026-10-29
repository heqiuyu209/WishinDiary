import json
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.core.research_policy import POLICY_VERSION
from app.ml import research_experiments as experiments
from app.ml.lifestyle_evaluation import PARAMETERS


@pytest.fixture
def registry(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, 'MODEL_PATH', tmp_path / 'model.skops')
    monkeypatch.setitem(PARAMETERS, 'n_estimators', 2)
    return tmp_path


def register(**changes):
    return experiments.register_protocol(calibration_cutoff='2022-10-01T00:00:00Z',
        test_cutoff='2023-04-01T00:00:00Z', data_as_of='2024-01-01T00:00:00Z',
        bootstrap_replicates=200, synthetic_users=3, **changes)


def test_immutable_protocol_freeze_run_replay_and_safe_registry(registry, assert_private_file, docker_application_layout, monkeypatch):
    run_id = register()
    assert experiments.list_experiments()[0]['kind'] == 'retrospective_exploration'
    digest = experiments.freeze_dataset(run_id, synthetic_only=True)
    path = experiments.run_directory(run_id)
    assert_private_file(path / 'dataset_snapshot.json')
    with pytest.raises(FileExistsError):
        experiments.freeze_dataset(run_id, synthetic_only=True)
    result = experiments.execute_experiment(run_id, publish_report=True)
    assert result['eligible_cases'] > 0
    assert experiments.execute_experiment(run_id, replay=True)['eligible_cases'] == result['eligible_cases']
    entry = experiments.list_experiments()[0]
    assert entry['status'] == 'complete' and entry['source'] == 'synthetic'
    assert 'data' not in entry and 'signature' not in entry and 'user_id' not in json.dumps(entry)
    from app.ml import lifestyle_report
    with monkeypatch.context() as image:
        image.setattr(lifestyle_report, '__file__', str(docker_application_layout / 'app/ml/lifestyle_report.py'))
        assert experiments.list_experiments()[0]['status'] == 'complete'
        assert lifestyle_report.read_lifestyle_report()['available']
    with pytest.raises(ValueError, match='already has'):
        experiments.execute_experiment(run_id)
    snapshot = json.loads((path / 'dataset_snapshot.json').read_text())
    assert snapshot['dataset_sha256'] == digest
    snapshot['data']['cycle_revisions'][0]['user_id'] = 12345
    (path / 'dataset_snapshot.json').write_text(json.dumps(snapshot))
    with pytest.raises(ValueError, match='artifact changed'):
        experiments.execute_experiment(run_id, replay=True)


def test_protocol_edits_path_escape_and_future_freeze_are_rejected(registry):
    run_id = register()
    path = experiments.run_directory(run_id) / 'protocol.json'
    plan = json.loads(path.read_text())
    plan['protocol']['test_cutoff'] = '2099-01-01T00:00:00Z'
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match='protocol changed'):
        experiments.read_protocol(run_id)
    assert experiments.list_experiments()[0]['status'] == 'invalid'
    with pytest.raises(ValueError, match='Invalid experiment ID'):
        experiments.run_directory('../../private')
    now = datetime.now(timezone.utc)
    future = experiments.register_protocol(calibration_cutoff=now - timedelta(days=1), test_cutoff=now + timedelta(days=1),
                                           data_as_of=now + timedelta(days=2))
    assert experiments.read_protocol(future)[0]['kind'] == 'prospective_plan'
    with pytest.raises(ValueError, match='has not been reached'):
        experiments.freeze_dataset(future, synthetic_only=True)


def test_frozen_real_snapshot_cannot_continue_after_withdrawal(registry, client, auth_header):
    assert client.put('/api/v1/research/participation', json={'participate': True,
        'policy_version': POLICY_VERSION, 'adult_confirmed': True}).status_code == 200
    run_id = register()
    experiments.freeze_dataset(run_id)
    assert client.put('/api/v1/research/participation', json={'participate': False}).status_code == 200
    with pytest.raises(ValueError, match='consent changed'):
        experiments.execute_experiment(run_id)
