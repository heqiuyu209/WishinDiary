"""Keep observed intervals independent of model eligibility."""

from alembic import op
import sqlalchemy as sa

revision = "0006_observed_intervals"
down_revision = "0005_prediction_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("chk_cycles_length", "cycles", type_="check")
    op.create_check_constraint("chk_cycles_length", "cycles", "cycle_length IS NULL OR cycle_length > 0")
    op.drop_constraint("chk_cycles_bleeding", "cycles", type_="check")
    op.create_check_constraint("chk_cycles_bleeding", "cycles", "bleeding_days IS NULL OR bleeding_days > 0")


def downgrade() -> None:
    # Do not truncate valid observations to satisfy the old model's bounds.
    count = op.get_bind().execute(sa.text(
        "SELECT COUNT(*) FROM cycles WHERE cycle_length > 120 OR bleeding_days > 30"
    )).scalar_one()
    if count:
        raise RuntimeError("Cannot downgrade: preserve/export long observations before restoring old bounds")
    op.drop_constraint("chk_cycles_length", "cycles", type_="check")
    op.create_check_constraint("chk_cycles_length", "cycles", "cycle_length IS NULL OR cycle_length BETWEEN 1 AND 120")
    op.drop_constraint("chk_cycles_bleeding", "cycles", type_="check")
    op.create_check_constraint("chk_cycles_bleeding", "cycles", "bleeding_days IS NULL OR bleeding_days BETWEEN 1 AND 30")
