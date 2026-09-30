"""Run reminder checks. Default is a read-only preview; --send enables SMTP.

python scripts/send_reminders.py --dry-run
python scripts/send_reminders.py --send
python scripts/send_reminders.py --send --loop
"""
import argparse
import json
from pathlib import Path
import signal
import sys
from threading import Event

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings, validate_security_baseline  # noqa: E402
from app.services.reminder_service import ReminderService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview counts without writing or sending (default)")
    mode.add_argument("--send", action="store_true", help="Claim reminders and deliver through configured SMTP")
    parser.add_argument("--loop", action="store_true", help="Check every five minutes until stopped")
    args = parser.parse_args()
    validate_security_baseline()
    if args.send and not settings.mail_enabled:
        print("SMTP is not configured or permitted; no reminders sent", file=sys.stderr)
        return 2
    stop = Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    service = ReminderService()
    while not stop.is_set():
        try:
            counts = service.run_once(send=args.send)
        except Exception:
            print("Reminder batch failed; check database and configuration", file=sys.stderr)
            if not args.loop:
                return 1
        else:
            print(json.dumps({"mode": "send" if args.send else "dry-run", **counts}), flush=True)
            if not args.loop:
                return 1 if counts["errors"] or counts["unknown"] else 0
        if not args.loop:
            return 0
        stop.wait(300)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
