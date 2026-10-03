"""Explicit missing values and timestamped research-field revisions."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0007_lifestyle_revisions"
down_revision = "0006_observed_intervals"
branch_labels = None
depends_on = None

NUMBERS = ("mood_level", "cramps_severity", "exercise_minutes", "sleep_duration_minutes", "sleep_quality")
FLAGS = ("is_exercise", "is_intercourse", "is_late_night", "is_medication")


def upgrade() -> None:
    for name in NUMBERS:
        op.alter_column("daily_logs", name, existing_type=sa.Integer(), nullable=True, server_default=None)
    for name in FLAGS:
        op.alter_column("daily_logs", name, existing_type=sa.Boolean(), nullable=True, server_default=None)
    for name in ("stress_level", "exercise_intensity", "sleep_start_minutes"):
        op.add_column("daily_logs", sa.Column(name, sa.Integer(), nullable=True))
    op.add_column("daily_logs", sa.Column("is_night_shift", sa.Boolean(), nullable=True))
    op.add_column("daily_logs", sa.Column("recording_version", sa.Integer(), nullable=False, server_default="0"))
    for name in ("recorded_at", "updated_at"):
        op.add_column("daily_logs", sa.Column(name, mysql.DATETIME(fsp=6), nullable=True))
    op.create_check_constraint("chk_daily_stress", "daily_logs", "stress_level BETWEEN 0 AND 3")
    op.create_check_constraint("chk_daily_intensity", "daily_logs", "exercise_intensity BETWEEN 0 AND 3")
    op.create_check_constraint("chk_daily_sleep_start", "daily_logs", "sleep_start_minutes BETWEEN 0 AND 1439")
    op.create_table(
        "daily_log_revisions",
        sa.Column("revision_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("log_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("log_date", sa.Date(), nullable=False),
        sa.Column("known_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("timezone_name", sa.String(64), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["log_id"], ["daily_logs.log_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.Index("idx_daily_revision_asof", "user_id", "log_date", "known_at", "revision_id"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4",
    )
    # An overwritten legacy row cannot prove what was known at its created_at.
    # Seed at migration time and mark it unusable for prospective features.
    op.execute("""
        INSERT INTO daily_log_revisions (log_id,user_id,log_date,known_at,timezone_name,source,payload)
        SELECT d.log_id,d.user_id,d.log_date,UTC_TIMESTAMP(6),u.notification_timezone,'legacy_unknown',
          JSON_OBJECT('sleep_duration_minutes',d.sleep_duration_minutes,'sleep_quality',d.sleep_quality,
            'is_late_night',d.is_late_night,'is_exercise',d.is_exercise,
            'exercise_minutes',d.exercise_minutes,'is_medication',d.is_medication)
        FROM daily_logs d JOIN users u ON u.user_id=d.user_id
    """)


def downgrade() -> None:
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM daily_logs WHERE recording_version > 0")).scalar_one():
        raise RuntimeError("Cannot downgrade: export and preserve new lifestyle records before removing nullable/revision semantics")
    op.drop_table("daily_log_revisions")
    for name in ("chk_daily_stress", "chk_daily_intensity", "chk_daily_sleep_start"):
        op.drop_constraint(name, "daily_logs", type_="check")
    for name in ("stress_level", "exercise_intensity", "sleep_start_minutes", "is_night_shift", "recording_version", "recorded_at", "updated_at"):
        op.drop_column("daily_logs", name)
    for name in NUMBERS:
        op.alter_column("daily_logs", name, existing_type=sa.Integer(), server_default="0",
                        nullable=name not in ("sleep_duration_minutes", "sleep_quality"))
    for name in FLAGS:
        op.alter_column("daily_logs", name, existing_type=sa.Boolean(), server_default="0",
                        nullable=name not in ("is_late_night", "is_medication"))
