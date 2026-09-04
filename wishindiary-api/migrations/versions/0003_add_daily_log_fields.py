"""daily_logs: add self-tracking fields (sleep/late-night, medication, symptom levels)

Revision ID: 0003_add_daily_log_fields
Revises: 0002_add_refresh_tokens
Create Date: 2026-09-04

与 migrations/legacy/006_add_daily_log_fields.sql 语义对齐，供自动化测试库
（conftest 通过 alembic upgrade head 建库）使用。
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_add_daily_log_fields"
down_revision = "0002_add_refresh_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "daily_logs",
        sa.Column("sleep_duration_minutes", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "daily_logs",
        sa.Column("sleep_quality", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "daily_logs",
        sa.Column("is_late_night", sa.Boolean(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "daily_logs",
        sa.Column("is_medication", sa.Boolean(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "daily_logs",
        sa.Column("medication_note", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "daily_logs",
        sa.Column(
            "symptom_levels",
            sa.JSON(),
            server_default=sa.text(
                "(JSON_OBJECT('headache',0,'bloat',0,'breast_tenderness',0,'fatigue',0))"
            ),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "chk_daily_sleep_duration", "daily_logs", "sleep_duration_minutes BETWEEN 0 AND 1440"
    )
    op.create_check_constraint(
        "chk_daily_sleep_quality", "daily_logs", "sleep_quality BETWEEN 0 AND 3"
    )


def downgrade() -> None:
    op.drop_constraint("chk_daily_sleep_quality", "daily_logs", type_="check")
    op.drop_constraint("chk_daily_sleep_duration", "daily_logs", type_="check")
    op.drop_column("daily_logs", "symptom_levels")
    op.drop_column("daily_logs", "medication_note")
    op.drop_column("daily_logs", "is_medication")
    op.drop_column("daily_logs", "is_late_night")
    op.drop_column("daily_logs", "sleep_quality")
    op.drop_column("daily_logs", "sleep_duration_minutes")
