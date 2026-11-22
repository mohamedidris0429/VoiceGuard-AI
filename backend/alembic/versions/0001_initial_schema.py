"""Initial schema: users, audio_analyses, reports.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-18
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("preferences", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "audio_analyses",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("stored_file_reference", sa.String(length=255), nullable=False),
        sa.Column("audio_duration", sa.Float(), nullable=True),
        sa.Column("sample_rate", sa.Integer(), nullable=True),
        sa.Column("channels", sa.Integer(), nullable=True),
        sa.Column("file_format", sa.String(length=16), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="upload"),
        sa.Column("predicted_class", sa.String(length=32), nullable=True),
        sa.Column("model_score", sa.Float(), nullable=True),
        sa.Column("model_version", sa.String(length=255), nullable=True),
        sa.Column(
            "analysis_status", sa.String(length=24), nullable=False, server_default="pending"
        ),
        sa.Column("failure_reason", sa.String(length=255), nullable=True),
        sa.Column("analysis_duration_ms", sa.Integer(), nullable=True),
        sa.Column("audio_features", sa.JSON(), nullable=True),
        sa.Column("model_details", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audio_analyses_user_id", "audio_analyses", ["user_id"])
    op.create_index(
        "ix_audio_analyses_user_created", "audio_analyses", ["user_id", "created_at"]
    )
    op.create_index(
        "ix_audio_analyses_user_status", "audio_analyses", ["user_id", "analysis_status"]
    )
    op.create_index(
        "ix_audio_analyses_user_class", "audio_analyses", ["user_id", "predicted_class"]
    )

    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "analysis_id",
            sa.Integer(),
            sa.ForeignKey("audio_analyses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("report_reference", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_reports_user_id", "reports", ["user_id"])
    op.create_index("ix_reports_analysis_id", "reports", ["analysis_id"], unique=True)
    op.create_index("ix_reports_report_reference", "reports", ["report_reference"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_reports_report_reference", table_name="reports")
    op.drop_index("ix_reports_analysis_id", table_name="reports")
    op.drop_index("ix_reports_user_id", table_name="reports")
    op.drop_table("reports")

    op.drop_index("ix_audio_analyses_user_class", table_name="audio_analyses")
    op.drop_index("ix_audio_analyses_user_status", table_name="audio_analyses")
    op.drop_index("ix_audio_analyses_user_created", table_name="audio_analyses")
    op.drop_index("ix_audio_analyses_user_id", table_name="audio_analyses")
    op.drop_table("audio_analyses")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
