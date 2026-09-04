"""刷新令牌（refresh token）表：支撑 Token 刷新与服务端撤销。

认证策略升级（TODO P0 安全项 5）：
- access token 仍为短期 JWT（HttpOnly Cookie），有效期由 ACCESS_TOKEN_EXPIRE_MINUTES 控制；
- 新增长期 refresh token（默认 30 天，配置项 REFRESH_TOKEN_EXPIRE_DAYS），
  以不透明随机串落库时仅存 SHA-256 摘要，即使库泄露也不可逆；
- 服务端撤销：刷新轮换（刷新即废弃旧 token）与退出登录（置 revoked_at），
  撤销状态保存在 MySQL，可跨进程/多实例共享。

Revision ID: 0002_add_refresh_tokens
Revises: 0001_initial_schema
Create Date: 2026-09-02
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_add_refresh_tokens"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "refresh_tokens",
        sa.Column("refresh_token_id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, index=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        # 非空表示该 token 已撤销（退出登录 / 刷新轮换），服务端据此拒绝
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("client_ip", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )


def downgrade() -> None:
    op.drop_table("refresh_tokens")
