"""Observed cycle revisions and voluntary tracking confirmations."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0008_cycle_research_events"
down_revision = "0007_lifestyle_revisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("cycle_history_reset_at", mysql.DATETIME(fsp=6), nullable=True))
    op.create_table("cycle_revisions",
        sa.Column("revision_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("cycle_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("known_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("timezone_name", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["cycle_id"], ["cycles.cycle_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.Index("idx_cycle_revision_asof", "user_id", "known_at", "revision_id"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4")
    op.execute("INSERT INTO cycle_revisions (cycle_id,user_id,start_date,end_date,known_at,source,timezone_name) "
               "SELECT c.cycle_id,c.user_id,c.start_date,c.end_date,UTC_TIMESTAMP(6),'legacy_snapshot',u.notification_timezone FROM cycles c JOIN users u ON u.user_id=c.user_id")
    op.create_table("cycle_tracking_events",
        sa.Column("event_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("cycle_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("anchor_start_date", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("known_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("timezone_name", sa.String(64), nullable=False),
        sa.CheckConstraint("kind IN ('unknown','missed_tracking','true_long_interval','no_onset')", name="chk_tracking_kind"),
        sa.ForeignKeyConstraint(["cycle_id"], ["cycles.cycle_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.Index("idx_tracking_asof", "user_id", "known_at", "event_id"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM cycle_tracking_events")).scalar_one():
        raise RuntimeError("Cannot downgrade with tracking confirmations; preserve authorized records first")
    if bind.execute(sa.text("SELECT COUNT(*) FROM cycle_revisions WHERE source<>'legacy_snapshot'")).scalar_one():
        raise RuntimeError("Cannot downgrade with cycle event history; preserve records first")
    if bind.execute(sa.text("SELECT COUNT(*) FROM users WHERE cycle_history_reset_at IS NOT NULL")).scalar_one():
        raise RuntimeError("Cannot downgrade with cycle history reset markers; preserve records first")
    op.drop_table("cycle_tracking_events")
    op.drop_table("cycle_revisions")
    op.drop_column("users", "cycle_history_reset_at")
