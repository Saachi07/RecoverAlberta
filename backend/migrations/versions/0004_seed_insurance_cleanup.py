"""seed insurance-type guides, cleanup orgs, and Indigenous pathway entries

Revision ID: 0004_seed_insurance_cleanup
Revises: 0003_seed_resources
Create Date: 2026-06-12

Inserts the resources added from the insurance-types / cleanup-arrangement /
Indigenous-benefits research doc (see `questions/resources.py`), following
the 0003 convention of a new migration per seed-list addition. Also updates
the `isc-emap` body to note that residents don't apply directly.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa
from alembic import op


revision = "0004_seed_insurance_cleanup"
down_revision = "0003_seed_resources"
branch_labels = None
depends_on = None


# Ids introduced by this migration, everything in questions/resources.py
# that postdates the 0003 seed.
NEW_IDS = [
    "team-rubicon-canada",
    "mennonite-disaster-service",
    "cleanup-insured-pathway",
    "cleanup-uninsured-pathway",
    "indigenous-insurance-pathway",
    "ins-guide-homeowners",
    "ins-guide-tenant",
    "ins-guide-condo",
    "ins-guide-auto",
    "ins-guide-rv",
    "ins-guide-boat",
    "ins-guide-farm",
    "ins-guide-crop",
    "ins-guide-livestock",
    "ins-guide-business",
    "ins-guide-commercial-property",
    "ins-guide-business-interruption",
    "ins-guide-life",
    "ins-guide-disability",
    "ins-guide-critical-illness",
    "ins-guide-extended-health",
    "ins-guide-travel",
    "ins-guide-mortgage",
]


def _load_seed_resources() -> list[dict]:
    """Import the hand-curated list from questions/resources.py."""
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
    seed = {r["id"]: r for r in _load_seed_resources()}

    existing_ids = {
        row[0]
        for row in bind.execute(sa.text("SELECT id FROM resources")).fetchall()
    }

    rows: list[dict] = []
    for rid in NEW_IDS:
        r = seed.get(rid)
        if r is None or rid in existing_ids:
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

    # Enriched EMAP body, residents don't apply directly; coordinated
    # through the band office / community.
    emap = seed.get("isc-emap")
    if emap and "isc-emap" in existing_ids:
        bind.execute(
            sa.text("UPDATE resources SET body = :body WHERE id = 'isc-emap'"),
            {"body": emap["body"]},
        )


def downgrade():
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM resources WHERE id IN :ids").bindparams(
            sa.bindparam("ids", expanding=True)
        ),
        {"ids": NEW_IDS},
    )
