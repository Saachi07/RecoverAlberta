-- Inventory evidence columns (inventory.md s2, s3).
--
-- case_items held one number (estimated_value) and no record of where it came
-- from. The photo inventory redesign needs a home for:
--   - a price range with its basis (replacement cost vs actual cash value),
--     date, and the comparable products behind it
--   - per-field confidence, so low-confidence fields can be flagged for review
--   - the taxonomy class, contents/building claim class, and bulk flag
--   - the damage vocabulary (multi-label) and where in which photo the item
--     was seen
--   - which component produced the row (model and version, rule id, or user)
--
-- estimated_value stays as the single headline number (the "mid" value, and
-- the replacement cost when price_basis is 'replacement'), so the existing
-- recommender, exports, and Inventory page keep working unchanged. Every new
-- column is nullable or defaulted; old rows and old clients are unaffected.
--
-- Row-level security is table-wide, so these columns inherit it.

alter table public.case_items
    add column if not exists price_low      numeric(12, 2),
    add column if not exists price_high     numeric(12, 2),
    add column if not exists price_basis    text,
    add column if not exists price_date     date,
    add column if not exists comparables    jsonb,
    add column if not exists field_confidence jsonb,
    add column if not exists taxonomy_id    text,
    add column if not exists claim_class    text,
    add column if not exists bulk           boolean not null default false,
    add column if not exists damage_types   text[],
    add column if not exists evidence       jsonb,
    add column if not exists source         text;

-- Constraints are dropped first so this file can be re-run.
alter table public.case_items drop constraint if exists case_items_price_range_ck;
alter table public.case_items add constraint case_items_price_range_ck
    check (
        (price_low is null or price_low >= 0)
        and (price_high is null or price_high >= 0)
        and (price_low is null or price_high is null or price_low <= price_high)
    );

alter table public.case_items drop constraint if exists case_items_price_basis_ck;
alter table public.case_items add constraint case_items_price_basis_ck
    check (price_basis is null or price_basis in ('replacement', 'acv'));

alter table public.case_items drop constraint if exists case_items_claim_class_ck;
alter table public.case_items add constraint case_items_claim_class_ck
    check (claim_class is null or claim_class in ('contents', 'building', 'unclear'));

alter table public.case_items drop constraint if exists case_items_comparables_ck;
alter table public.case_items add constraint case_items_comparables_ck
    check (comparables is null or jsonb_typeof(comparables) = 'array');

alter table public.case_items drop constraint if exists case_items_field_confidence_ck;
alter table public.case_items add constraint case_items_field_confidence_ck
    check (field_confidence is null or jsonb_typeof(field_confidence) = 'object');

alter table public.case_items drop constraint if exists case_items_evidence_ck;
alter table public.case_items add constraint case_items_evidence_ck
    check (evidence is null or jsonb_typeof(evidence) = 'object');

-- Lookups the app is likely to need: totals by claim class, bulk-entry flags.
create index if not exists case_items_claim_class_idx
    on public.case_items(user_id, claim_class);
