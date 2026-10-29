"""Audit legacy cycle history; applying changes requires a private backup."""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import transaction


def plan_repairs(rows: list[dict]) -> list[dict]:
    """Derive lengths and clear only the inconsistent legacy auto-close pattern."""
    ordered = sorted(rows, key=lambda row: (row["user_id"], row["start_date"]))
    repairs = []
    for index, row in enumerate(ordered):
        following = ordered[index + 1] if index + 1 < len(ordered) else None
        if following and following["user_id"] != row["user_id"]:
            following = None
        length = (following["start_date"] - row["start_date"]).days if following else None
        # Respect the database's existing length constraint; report these separately.
        if length is not None and not 1 <= length <= 120:
            continue
        end, bleeding = row["end_date"], row["bleeding_days"]
        legacy = (
            following is not None
            and end == following["start_date"]
            and bleeding == 5
            and row["cycle_length"] == length
            and (end - row["start_date"]).days + 1 != bleeding
        )
        if legacy:
            end, bleeding = None, None
        if (row["cycle_length"], row["end_date"], row["bleeding_days"]) != (length, end, bleeding):
            repairs.append({
                "before": dict(row),
                "after": {"cycle_length": length, "end_date": end, "bleeding_days": bleeding},
            })
    return repairs


def repair_history(*, apply: bool = False, backup: Path | None = None) -> dict:
    with transaction() as connection:
        with connection.cursor() as cursor:
            # Match the application's write lock order to prevent concurrent edits.
            cursor.execute("SELECT user_id FROM users ORDER BY user_id FOR UPDATE")
            cursor.fetchall()
            cursor.execute("SELECT cycle_id, user_id, start_date, end_date, cycle_length, "
                           "bleeding_days FROM cycles ORDER BY user_id, start_date FOR UPDATE")
            rows = cursor.fetchall()
            repairs = plan_repairs(rows)
            invalid_gaps = sum(
                a["user_id"] == b["user_id"] and (b["start_date"] - a["start_date"]).days > 120
                for a, b in zip(rows, rows[1:])
            )
            if apply and repairs:
                if backup is None:
                    raise ValueError("--apply requires --backup outside the repository")
                repo = Path(__file__).resolve().parents[2]
                if backup.resolve().is_relative_to(repo):
                    raise ValueError("Backup contains private dates; choose a path outside the repository")
                backup.parent.mkdir(parents=True, exist_ok=True)
                # Exclusive creation prevents overwriting a previous recovery copy.
                fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(repairs, handle, ensure_ascii=False, indent=2, default=str)
                    handle.flush()
                    os.fsync(handle.fileno())
                for item in repairs:
                    before, after = item["before"], item["after"]
                    cursor.execute(
                        "UPDATE cycles SET cycle_length=%s, end_date=%s, bleeding_days=%s "
                        "WHERE cycle_id=%s AND user_id=%s",
                        (after["cycle_length"], after["end_date"], after["bleeding_days"],
                         before["cycle_id"], before["user_id"]),
                    )
    return {"mode": "apply" if apply else "dry_run", "records_scanned": len(rows),
            "records_to_repair": len(repairs), "gaps_requiring_manual_review": invalid_gaps}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup", type=Path, help="Private recovery JSON outside the repository")
    args = parser.parse_args()
    print(json.dumps(repair_history(apply=args.apply, backup=args.backup)))


if __name__ == "__main__":
    main()
