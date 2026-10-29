"""Register, freeze, run and replay fixed local research experiments."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ml.research_experiments import execute_experiment, freeze_dataset, list_experiments, register_protocol


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    register = commands.add_parser('register')
    for name in ('calibration-cutoff', 'test-cutoff', 'data-as-of'):
        register.add_argument(f'--{name}', required=True)
    register.add_argument('--bootstrap-replicates', type=int, default=1000)
    register.add_argument('--synthetic-users', type=int, default=12)
    freeze = commands.add_parser('freeze')
    freeze.add_argument('run_id')
    sources = freeze.add_mutually_exclusive_group(required=True)
    sources.add_argument('--synthetic-only', action='store_true')
    sources.add_argument('--database', action='store_true')
    freeze.add_argument('--acknowledge-authorized-data', action='store_true')
    for name in ('run', 'replay'):
        run = commands.add_parser(name)
        run.add_argument('run_id')
        run.add_argument('--publish-report', action='store_true')
    commands.add_parser('list')
    args = parser.parse_args()
    if args.command == 'register':
        for value in (args.calibration_cutoff, args.test_cutoff, args.data_as_of):
            from datetime import datetime
            if datetime.fromisoformat(value.replace('Z', '+00:00')).tzinfo is None:
                parser.error('Protocol dates require explicit timezone offsets')
        print(register_protocol(calibration_cutoff=args.calibration_cutoff, test_cutoff=args.test_cutoff,
            data_as_of=args.data_as_of, bootstrap_replicates=args.bootstrap_replicates, synthetic_users=args.synthetic_users))
    elif args.command == 'freeze':
        if args.database and not args.acknowledge_authorized_data:
            parser.error('Database snapshots require --acknowledge-authorized-data and active in-app consent')
        print(json.dumps({'run_id': args.run_id, 'dataset_sha256': freeze_dataset(args.run_id, synthetic_only=args.synthetic_only)}))
    elif args.command in ('run', 'replay'):
        print(json.dumps(execute_experiment(args.run_id, replay=args.command == 'replay', publish_report=args.publish_report)))
    else:
        print(json.dumps(list_experiments(), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
