"""Independent research consent events and self-reported medical context."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0009_research_participation"
down_revision = "0008_cycle_research_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("research_consent_events",
        sa.Column("event_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("policy_version", sa.String(32), nullable=False),
        sa.Column("episode_id", sa.String(32), nullable=False),
        sa.Column("known_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint("action IN ('grant','withdraw')", name="chk_research_action"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.Index("idx_research_consent_user", "user_id", "event_id"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4")
    op.create_table("research_background_revisions",
        sa.Column("revision_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("known_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("timezone_name", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.Index("idx_research_background_asof", "user_id", "known_at", "revision_id"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4")


def downgrade() -> None:
    bind = op.get_bind()
    for table in ("research_consent_events", "research_background_revisions"):
        if bind.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar_one():
            raise RuntimeError("Cannot downgrade with research consent or background history; preserve records first")
    op.drop_table("research_background_revisions")
    op.drop_table("research_consent_events")

