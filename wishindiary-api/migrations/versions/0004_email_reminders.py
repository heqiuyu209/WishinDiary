"""Verified email, opt-in reminder preferences, and durable send claims."""
from alembic import op
import sqlalchemy as sa

revision = "0004_email_reminders"
down_revision = "0003_add_daily_log_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email", sa.String(254), nullable=True))
    op.create_index("uq_users_email", "users", ["email"], unique=True)
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("reminder_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    op.add_column("users", sa.Column("reminder_lead_days", sa.SmallInteger(), nullable=False, server_default=sa.text("2")))
    op.add_column("users", sa.Column("notification_timezone", sa.String(64), nullable=False, server_default="Asia/Shanghai"))
    op.create_check_constraint("chk_reminder_lead", "users", "reminder_lead_days BETWEEN 1 AND 3")
    op.create_table(
        "email_verifications",
        sa.Column("user_id", sa.Integer(), primary_key=True),
        sa.Column("pending_email", sa.String(254), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=False),
        sa.Column("attempts", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4",
    )
    op.create_table(
        "reminder_deliveries",
        sa.Column("delivery_id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("cycle_start_date", sa.Date(), nullable=False),
        sa.Column("predicted_date", sa.Date(), nullable=False),
        sa.Column("reminder_date", sa.Date(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("user_id", "cycle_start_date", name="uq_reminder_cycle"),
        sa.CheckConstraint("state IN ('sending', 'sent', 'unknown', 'canceled')", name="chk_reminder_state"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4",
    )


def downgrade() -> None:
    op.drop_table("reminder_deliveries")
    op.drop_table("email_verifications")
    op.drop_constraint("chk_reminder_lead", "users", type_="check")
    op.drop_index("uq_users_email", table_name="users")
    for column in ("notification_timezone", "reminder_lead_days", "reminder_enabled", "email_verified_at", "email"):
        op.drop_column("users", column)
