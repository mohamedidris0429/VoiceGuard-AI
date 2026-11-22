"""Phase 2: segment-wise detection storage.

Adds the ``analysis_segments`` table (one row per analysed window) and a
nullable ``audio_analyses.segment_meta`` JSON column holding the window/hop
plan and the aggregate. Both changes are additive and nullable, so existing
rows and the Phase 1 read endpoints keep working unchanged.

Revision ID: 0002_segments
Revises: 0001_initial
Create Date: 2026-11-22
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_segments"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("audio_analyses", sa.Column("segment_meta", sa.JSON(), nullable=True))

    op.create_table(
        "analysis_segments",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "analysis_id",
            sa.Integer(),
            sa.ForeignKey("audio_analyses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("start_seconds", sa.Float(), nullable=False),
        sa.Column("end_seconds", sa.Float(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="done"),
        sa.Column("label", sa.String(length=32), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.Column("model_version", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "analysis_id", "segment_index", name="uq_analysis_segments_analysis_index"
        ),
    )
    op.create_index(
        "ix_analysis_segments_analysis_id", "analysis_segments", ["analysis_id"]
    )
    op.create_index(
        "ix_analysis_segments_analysis_order",
        "analysis_segments",
        ["analysis_id", "segment_index"],
    )


def downgrade() -> None:
    op.drop_index("ix_analysis_segments_analysis_order", table_name="analysis_segments")
    op.drop_index("ix_analysis_segments_analysis_id", table_name="analysis_segments")
    op.drop_table("analysis_segments")
    op.drop_column("audio_analyses", "segment_meta")
