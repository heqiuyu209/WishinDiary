"""初始数据库结构。

基于原 schema.sql 的统一基线（users / cycles / daily_logs / prediction_logs），
并新增 login_attempts 表用于可共享的登录限流（跨进程/实例，基于 MySQL）。

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-01
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. 用户表
    op.create_table(
        "users",
        sa.Column("user_id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("username", sa.String(length=50), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )

    # 2. 生理周期表（唯一索引防重复打卡 + 外键级联删除）
    op.create_table(
        "cycles",
        sa.Column("cycle_id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("cycle_length", sa.Integer(), nullable=True),
        sa.Column("bleeding_days", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.UniqueConstraint("user_id", "start_date", name="uk_user_start"),
        sa.CheckConstraint("end_date IS NULL OR end_date >= start_date", name="chk_cycles_range"),
        sa.CheckConstraint("cycle_length IS NULL OR cycle_length BETWEEN 1 AND 120", name="chk_cycles_length"),
        sa.CheckConstraint("bleeding_days IS NULL OR bleeding_days BETWEEN 1 AND 30", name="chk_cycles_bleeding"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )

    # 3. 每日精细化健康打卡与日志表
    op.create_table(
        "daily_logs",
        sa.Column("log_id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("log_date", sa.Date(), nullable=False),
        sa.Column("mood_level", sa.Integer(), server_default=sa.text("0"), nullable=True),
        sa.Column("cramps_severity", sa.Integer(), server_default=sa.text("0"), nullable=True),
        sa.Column("is_exercise", sa.Boolean(), server_default=sa.text("0"), nullable=True),
        sa.Column("is_intercourse", sa.Boolean(), server_default=sa.text("0"), nullable=True),
        sa.Column("exercise_type", sa.String(length=50), nullable=True),
        sa.Column("exercise_minutes", sa.Integer(), server_default=sa.text("0"), nullable=True),
        sa.Column("diet_tag", sa.String(length=100), nullable=True),
        sa.Column("journal_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.UniqueConstraint("user_id", "log_date", name="uk_user_date"),
        sa.CheckConstraint("mood_level BETWEEN 0 AND 3", name="chk_daily_mood"),
        sa.CheckConstraint("cramps_severity BETWEEN 0 AND 3", name="chk_daily_cramps"),
        sa.CheckConstraint("exercise_minutes >= 0", name="chk_daily_exercise_minutes"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )

    # 4. AI 预测日志与误差对账表
    op.create_table(
        "prediction_logs",
        sa.Column("pred_id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("predicted_date", sa.Date(), nullable=False),
        sa.Column("actual_date", sa.Date(), nullable=True),
        sa.Column("error_days", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("idx_prediction_pending", "prediction_logs", ["user_id", "actual_date", "created_at"])

    # 5. 登录限流表（可共享：多实例基于同一 MySQL 计数）
    op.create_table(
        "login_attempts",
        sa.Column("attempt_id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("client_key", sa.String(length=255), nullable=False),
        sa.Column("attempted_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("success", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Index("idx_login_attempts_key_time", "client_key", "attempted_at"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )


def downgrade() -> None:
    # MySQL 外键约束依赖 user_id 上的索引（predictions/cycles/daily_logs 引用了 users），
    # 显式 DROP INDEX 会触发 1553（Cannot drop index: needed in a foreign key constraint）。
    # 因此在 MySQL 上必须先删引用方（子表），DROP TABLE 会随表一并删除其索引与外键，
    # 最后删除被引用的 users 父表；login_attempts 无外键，可随时删除。
    op.drop_table("prediction_logs")
    op.drop_table("daily_logs")
    op.drop_table("cycles")
    op.drop_table("login_attempts")
    op.drop_table("users")
