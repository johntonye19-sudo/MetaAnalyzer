"""add evidence, metadata records, and chain-of-custody events

Revision ID: 0003
Revises: 0002
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
derives_from: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "evidence",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("investigation_id", sa.Integer(), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("declared_content_type", sa.String(length=255), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False, unique=True),
        sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("extraction_status", sa.String(length=32), nullable=False, server_default="pending"),
    )
    op.create_index("ix_evidence_sha256", "evidence", ["sha256"])
    op.create_index("ix_evidence_investigation_uploaded", "evidence", ["investigation_id", "uploaded_at"])

    op.create_table(
        "metadata_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("evidence_id", sa.String(length=36), sa.ForeignKey("evidence.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("tool_version", sa.String(length=128), nullable=True),
        sa.Column("values", sa.JSON(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_metadata_records_evidence_id", "metadata_records", ["evidence_id"])

    op.create_table(
        "chain_of_custody_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("evidence_id", sa.String(length=36), sa.ForeignKey("evidence.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("evidence_id", "action", "occurred_at", name="uq_custody_event_time"),
    )
    op.create_index("ix_chain_of_custody_events_evidence_id", "chain_of_custody_events", ["evidence_id"])


def downgrade() -> None:
    op.drop_index("ix_chain_of_custody_events_evidence_id", table_name="chain_of_custody_events")
    op.drop_table("chain_of_custody_events")
    op.drop_index("ix_metadata_records_evidence_id", table_name="metadata_records")
    op.drop_table("metadata_records")
    op.drop_index("ix_evidence_investigation_uploaded", table_name="evidence")
    op.drop_index("ix_evidence_sha256", table_name="evidence")
    op.drop_table("evidence")
