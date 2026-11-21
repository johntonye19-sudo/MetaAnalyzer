"""add investigations and investigation access table

Revision ID: 0002
Revises: 0001
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
derives_from: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "investigations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=4000), nullable=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_investigations_owner_id", "investigations", ["owner_id"])

    op.create_table(
        "investigation_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("investigation_id", sa.Integer(), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("investigation_id", "user_id", name="uq_investigation_member"),
    )
    op.create_index("ix_investigation_members_investigation_id", "investigation_members", ["investigation_id"])
    op.create_index("ix_investigation_members_user_id", "investigation_members", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_investigation_members_user_id", table_name="investigation_members")
    op.drop_index("ix_investigation_members_investigation_id", table_name="investigation_members")
    op.drop_table("investigation_members")
    op.drop_index("ix_investigations_owner_id", table_name="investigations")
    op.drop_table("investigations")
