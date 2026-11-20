"""Store review hyperlinks and widen review state storage."""

from alembic import op
import sqlalchemy as sa

revision = "9f2618a85e01"
down_revision = "dde01f06eaf1"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("reviews") as batch:
        batch.add_column(sa.Column("url", sa.Text(), nullable=True))
        batch.alter_column("state", existing_type=sa.String(16), type_=sa.String(32), existing_nullable=False)


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text(
        "SELECT 1 FROM reviews WHERE url IS NOT NULL OR length(state) > 16 LIMIT 1"
    )).first():
        raise RuntimeError("Downgrade would discard review links or states. Restore from a backup to roll back.")
    with op.batch_alter_table("reviews") as batch:
        batch.drop_column("url")
        batch.alter_column("state", existing_type=sa.String(32), type_=sa.String(16), existing_nullable=False)
