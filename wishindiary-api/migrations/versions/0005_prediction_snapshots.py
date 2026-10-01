"""Immutable first forecast per cycle; legacy forecasts remain unanchored."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0005_prediction_snapshots"
down_revision = "0004_email_reminders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Historical logs cannot be assigned an anchor without guessing after the fact.
    for column in (
        sa.Column("anchor_start_date", sa.Date(), nullable=True),
        sa.Column("issued_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("prediction_method", sa.String(32), nullable=True),
        sa.Column("model_version", sa.String(80), nullable=True),
        sa.Column("model_sha256", sa.String(64), nullable=True),
        sa.Column("interval_low", sa.Float(), nullable=True),
        sa.Column("interval_high", sa.Float(), nullable=True),
    ):
        op.add_column("prediction_logs", column)
    op.create_index("uq_prediction_anchor", "prediction_logs", ["user_id", "anchor_start_date"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_prediction_anchor", table_name="prediction_logs")
    for name in ("interval_high", "interval_low", "model_sha256", "model_version",
                 "prediction_method", "issued_at", "anchor_start_date"):
        op.drop_column("prediction_logs", name)
