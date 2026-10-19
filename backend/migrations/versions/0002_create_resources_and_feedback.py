"""create resources and case_resource_feedback tables

Revision ID: 0002_create_resources_and_feedback
Revises: 51974c14c187
Create Date: 2026-06-09

"""
from alembic import op
import sqlalchemy as sa


revision = "0002_create_resources_and_feedback"
down_revision = "51974c14c187"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "resources",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("url", sa.String(length=512), nullable=True),
        sa.Column("phone", sa.String(length=64), nullable=True),
        sa.Column("region", sa.String(length=32), nullable=False, server_default="*"),
        sa.Column("disaster_types", sa.JSON(), nullable=False),
        sa.Column("supports_plans", sa.JSON(), nullable=False),
        sa.Column("requires", sa.JSON(), nullable=False),
        sa.Column("excludes", sa.JSON(), nullable=False),
        sa.Column("insurance_companies", sa.JSON(), nullable=True),
        sa.Column("eligibility_days", sa.Integer(), nullable=True),
        sa.Column("scraped_at", sa.String(length=32), nullable=True),
        sa.Column("max_benefit_cad", sa.Integer(), nullable=True),
        sa.Column("priority_floor", sa.Float(), nullable=False, server_default="0"),
        sa.Column("tags_added", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "case_resource_feedback",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("case_id", sa.Integer(), nullable=False),
        sa.Column("resource_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["recovery_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id", "resource_id", name="uq_case_resource_feedback"),
    )
    op.create_index(
        "ix_case_resource_feedback_case_id",
        "case_resource_feedback",
        ["case_id"],
    )
    op.create_index(
        "ix_case_resource_feedback_resource_id",
        "case_resource_feedback",
        ["resource_id"],
    )


def downgrade():
    op.drop_index("ix_case_resource_feedback_resource_id", table_name="case_resource_feedback")
    op.drop_index("ix_case_resource_feedback_case_id", table_name="case_resource_feedback")
    op.drop_table("case_resource_feedback")
    op.drop_table("resources")
