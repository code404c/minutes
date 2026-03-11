"""add indexes for jobs status and created_at

Revision ID: 20260312_0002
Revises: 20260311_0001
Create Date: 2026-03-12 02:00:00
"""

from __future__ import annotations

from alembic import op


revision = "20260312_0002"
down_revision = "20260311_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_jobs_status", "jobs", ["status"], unique=False)
    op.create_index("ix_jobs_created_at", "jobs", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_jobs_created_at", table_name="jobs")
    op.drop_index("ix_jobs_status", table_name="jobs")
