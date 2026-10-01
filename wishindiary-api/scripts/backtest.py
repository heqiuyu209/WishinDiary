"""Offline full-pipeline backtest; reports aggregates and never replaces weights."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from app.core.config import settings
from app.features import load_cycle_training_data
from app.ml.forecast_evaluation import pipeline_fingerprint, run_forecast_backtest
from scripts.generate_clean_training_data import build_synthetic_training_data
from scripts.train import _collect_env_metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--synthetic-only', action='store_true', help='Use synthetic demonstration cycles only')
    source.add_argument('--csv', type=Path, help='Authorized cycle CSV with user_id/start_date/cycle_length/bleeding_days')
    source.add_argument('--database', action='store_true', help='Use independently authorized user database records')
    parser.add_argument('--output-dir', type=Path, help='Defaults to MODEL_PATH directory')
    args = parser.parse_args()
    if args.synthetic_only:
        cycles, _ = build_synthetic_training_data()
        source_name = 'synthetic'
    elif args.csv:
        cycles = pd.read_csv(args.csv)
        source_name = 'authorized_csv'
    else:
        cycles, _ = load_cycle_training_data(clean=False)
        source_name = 'authorized_database'
    # Canonical ordering makes fingerprints independent of CSV/database row order.
    canonical = cycles.sort_values(['user_id', 'start_date']).to_json(orient='records', date_format='iso')
    report = {
        'schema_version': 1,
        'metadata': _collect_env_metadata(),
        'pipeline_sha256': pipeline_fingerprint(),
        'dataset': {'source': source_name, 'total_cycles': len(cycles),
                    'n_users': int(cycles.user_id.nunique()),
                    'fingerprint': hashlib.sha256(canonical.encode()).hexdigest()},
        'evaluation': run_forecast_backtest(cycles),
        'notes': [
            '模型仅使用截点前已完成的训练标签，截点后保持冻结；个人历史逐周期更新。',
            '模型未见用户指未进入全局训练的用户，仍允许使用其预测时已知的个人历史。',
            '每个方法使用同一批样本，均值/中位数采用最近三次，指数平滑 alpha=0.5；全部取整并限制在 21–45 天。',
            '树分位区间与基础统计区间分别报告经验覆盖率，不是经过校准的 90% 预测区间。',
            '本报告评估算法流程与重新训练的折内模型，不代表当前部署权重的实测准确率。',
            '只输出汇总，不保存个人记录；合成数据仅用于验证研究流程。',
        ],
    }
    directory = args.output_dir or settings.model_abs_path.parent
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'forecast_evaluation_report.json'
    # Fail rather than serialize NaN/Infinity or replace a valid report on error.
    payload = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(payload, encoding='utf-8')
    temporary.replace(path)
    print(f'Full-pipeline backtest report: {path}')
    for name, result in report['evaluation']['protocols'].items():
        print(f"{name}: {result['samples']} samples; MAE {result['models'].get('online_pipeline', {}).get('mae', 'unavailable')}")


if __name__ == '__main__':
    main()
