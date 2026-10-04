"""Invalidate frozen research snapshots after health-record deletion."""
from alembic import op
import sqlalchemy as sa

revision = '0010_research_deletion_epoch'
down_revision = '0009_research_participation'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('research_data_epoch', sa.BigInteger(), server_default='0', nullable=False))


def downgrade():
    if op.get_bind().execute(sa.text('SELECT COUNT(*) FROM users WHERE research_data_epoch<>0')).scalar_one():
        raise RuntimeError('Cannot drop research deletion markers; preserve the invalidation boundary')
    op.drop_column('users', 'research_data_epoch')
