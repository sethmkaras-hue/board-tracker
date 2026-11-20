"""Store review start overrides and reviewer assignments."""

from alembic import op
import sqlalchemy as sa

revision = "8e7b42d716fa"
down_revision = "9f2618a85e01"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("reviews", sa.Column("review_start_date", sa.Date(), nullable=True))
    op.create_table(
        "review_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("review_id", sa.Integer(), sa.ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reviewer_id", sa.Integer(), sa.ForeignKey("people.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("allocation_status", sa.String(16), server_default="Not Allocated", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("review_id", "reviewer_id", name="review_assignments_review_reviewer_key"),
        sa.CheckConstraint("allocation_status IN ('Not Allocated', 'Allocated')", name="allocation_status_valid"),
    )
    op.create_index("ix_review_assignments_reviewer_id", "review_assignments", ["reviewer_id"])


def downgrade():
    bind = op.get_bind()
    if (bind.execute(sa.text("SELECT 1 FROM review_assignments LIMIT 1")).first()
            or bind.execute(sa.text("SELECT 1 FROM reviews WHERE review_start_date IS NOT NULL LIMIT 1")).first()):
        raise RuntimeError("Downgrade would discard reviewer assignments or review start overrides.")
    op.drop_table("review_assignments")
    with op.batch_alter_table("reviews") as batch:
        batch.drop_column("review_start_date")
