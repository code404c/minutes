"""init jobs table

Revision ID: 20260311_0001
Revises:
Create Date: 2026-03-11 20:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260311_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("profile", sa.String(length=64), nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=False),
        sa.Column("source_content_type", sa.String(length=255), nullable=True),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("normalized_path", sa.Text(), nullable=True),
        sa.Column("output_dir", sa.Text(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("language", sa.String(length=32), nullable=True),
        sa.Column("hotwords_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("sync_mode", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("jobs")

