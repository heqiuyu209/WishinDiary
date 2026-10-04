import json

import pytest

from app.core.config import settings
from app.services.research_service import read_evaluation_report
from scripts import backtest, train


def test_old_database_cli_cannot_bypass_event_based_research_consent(monkeypatch):
    with pytest.raises(ValueError, match='active consent'):
        train.train_and_evaluate()
    monkeypatch.setattr('sys.argv', ['backtest.py', '--database'])
    with pytest.raises(SystemExit) as error:
        backtest.main()
    assert error.value.code == 2


def test_legacy_mysql_reports_cannot_remain_visible_after_governance_upgrade(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, 'MODEL_PATH', tmp_path / 'model.skops')
    (tmp_path / 'model_evaluation_report.json').write_text(json.dumps({'dataset': {'source': 'mysql'}}))
    report = read_evaluation_report()
    assert not report['available'] and '授权' in report['message']
