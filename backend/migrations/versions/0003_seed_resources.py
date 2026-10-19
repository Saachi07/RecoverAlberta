"""seed resources table from questions/resources.py

Revision ID: 0003_seed_resources
Revises: 0002_create_resources_and_feedback
Create Date: 2026-06-09

Pulls the hand-curated RESOURCES list from `questions/resources.py` into
the resources table. Idempotent at row level (skip if id exists) so
re-running upgrade after a partial failure won't crash.

If anyone later adds resources to the seed list, they should add a NEW
migration that inserts those specific rows, don't re-run this one.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa
from alembic import op


revision = "0003_seed_resources"
down_revision = "0002_create_resources_and_feedback"
branch_labels = None
depends_on = None


def _load_seed_resources() -> list[dict]:
    """Import the hand-curated list from questions/resources.py.

    Migrations don't normally reach across into sibling packages, but
    this is a one-shot seed and keeping the seed data colocated with
    the standalone recommender (so recommend_demo.py keeps working) is
    worth the small ugliness.
    """
    repo_root = Path(__file__).resolve().parents[3]
    questions_dir = repo_root / "questions"
    if str(questions_dir) not in sys.path:
        sys.path.insert(0, str(questions_dir))

    from resources import RESOURCES  # type: ignore  (importable at runtime)
    return RESOURCES


def upgrade():
    bind = op.get_bind()
    resources_tbl = sa.table(
        "resources",
        sa.column("id", sa.String),
        sa.column("type", sa.String),
        sa.column("title", sa.String),
        sa.column("body", sa.Text),
        sa.column("url", sa.String),
        sa.column("phone", sa.String),
        sa.column("region", sa.String),
        sa.column("disaster_types", sa.JSON),
        sa.column("supports_plans", sa.JSON),
        sa.column("requires", sa.JSON),
        sa.column("excludes", sa.JSON),
        sa.column("insurance_companies", sa.JSON),
        sa.column("eligibility_days", sa.Integer),
        sa.column("scraped_at", sa.String),
        sa.column("max_benefit_cad", sa.Integer),
        sa.column("priority_floor", sa.Float),
        sa.column("tags_added", sa.JSON),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )

    now = datetime.now(timezone.utc)
    seed = _load_seed_resources()

    existing_ids = {
        row[0]
        for row in bind.execute(sa.text("SELECT id FROM resources")).fetchall()
    }

    rows: list[dict] = []
    for r in seed:
        if r["id"] in existing_ids:
            continue
        rows.append({
            "id": r["id"],
            "type": r["type"],
            "title": r["title"],
            "body": r["body"],
            "url": r.get("url"),
            "phone": r.get("phone"),
            "region": r.get("region", "*") if isinstance(r.get("region"), str) else "*",
            "disaster_types": r.get("disaster_types") or ["*"],
            "supports_plans": r.get("supports_plans") or [],
            "requires": r.get("requires") or [],
            "excludes": r.get("excludes") or [],
            "insurance_companies": r.get("insurance_companies"),
            "eligibility_days": r.get("eligibility_days"),
            "scraped_at": r.get("scraped_at"),
            "max_benefit_cad": r.get("max_benefit_cad"),
            "priority_floor": float(r.get("priority_floor") or 0.0),
            "tags_added": r.get("tags_added") or [],
            "created_at": now,
            "updated_at": now,
        })

    if rows:
        op.bulk_insert(resources_tbl, rows)


def downgrade():
    seed = _load_seed_resources()
    ids = [r["id"] for r in seed]
    if not ids:
        return
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM resources WHERE id IN :ids").bindparams(
            sa.bindparam("ids", expanding=True)
        ),
        {"ids": ids},
    )
