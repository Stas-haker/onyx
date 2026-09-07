"""Local meeting metadata, scoped to the existing Onyx user and tenant schema."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e170cab903a1"
down_revision = "856bcbe14d79"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "local_meeting",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("agenda", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("duration", sa.Float()),
        sa.Column("error", sa.Text()),
        sa.Column("segments", postgresql.JSONB(), nullable=False),
        sa.Column("analysis", postgresql.JSONB()),
    )
    op.create_index("ix_local_meeting_user_id", "local_meeting", ["user_id"])


def downgrade() -> None:
    op.drop_table("local_meeting")
