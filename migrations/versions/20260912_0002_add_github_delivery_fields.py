"""add GitHub delivery fields to tasks

Revision ID: 20260912_0002
Revises: 20260903_0001
Create Date: 2026-09-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260912_0002"
down_revision: Union[str, None] = "20260903_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tasks", sa.Column("github_delivery_id", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "tasks", sa.Column("github_event", sa.String(length=50), nullable=True)
    )
    op.add_column(
        "tasks", sa.Column("github_action", sa.String(length=50), nullable=True)
    )
    op.create_index(
        "ix_tasks_github_delivery_id",
        "tasks",
        ["github_delivery_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_tasks_github_delivery_id", table_name="tasks")
    op.drop_column("tasks", "github_action")
    op.drop_column("tasks", "github_event")
    op.drop_column("tasks", "github_delivery_id")
