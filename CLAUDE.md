# CLAUDE.md: Rebuildr orientation

Disaster-recovery web app for Alberta (AI4Good Lab project). A user creates a case after a disaster, scans rooms into an inventory with estimated values, uploads insurance documents for plain-language summaries and deadlines, and gets a recommended list of recovery programs.

## Layout
- `frontend/`: React 18 + TypeScript + Vite + react-router. `src/pages` (screens), `src/components` (incl. `claim/`, `analysis/`, `forms/`), `src/lib` (helpers, `validation.ts`), `src/api.ts` (all backend calls), `src/auth` (Supabase auth; demo mode via `VITE_DISABLE_AUTH`), `src/pages/legal` + `src/legal/business.ts` (legal pages and operator details). Tests: `npm test` (vitest).
- `backend/`: Flask API on Supabase (Postgres, Auth, Storage). `app/blueprints` = routes (auth, cases, items, documents, ml, ale, communications, alerts, terms, me, meta, health, recommendations). `app/services` = `gemini_client` (retry/fallback), `gemini_inventory` (photo to items), `gemini_documents` (PDF/image analysis), `document_pipeline`, `content_filter` + `signals` + `tags` (TF-IDF recommender), `program_scraper`, `weather_alerts`, `ai_guard` (prompt-injection defense), `rate_limit`, `upload_validation`. SQL in `supabase/migrations/` (apply in order). Deployed via `render.yaml`.
- `pdf_and_summary/`: document text extraction, OCR, spaCy NER, redaction, summarizer, verification. Used by the backend document flow.
- `questions/`: intake questions, routing rules, resources, recommender prototype (root `tests/` cover it). The backend recommender lives in `backend/app/services/content_filter.py`.
- `ml/`: standalone Flask experiment (YOLO-World counting, ViT damage classifier trained on chairs/tables only). NOT wired into the web app. The live photo scan is `backend/app/services/gemini_inventory.py`.
- `tests/` (root, pytest) and `backend/tests/`.

## Run
- Backend: `cd backend; python -m venv .venv; pip install -r requirements.txt; python -m spacy download en_core_web_sm`; copy `.env.example` to `.env`; `python run.py` (port 5000). Health: `GET /health`.
- Frontend: `cd frontend; npm ci; npm run dev` (port 5173). Needs `VITE_API_BASE`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`.
- Tests: `pytest tests backend/tests` (from repo root/backend), `cd frontend; npm test`, `npx tsc -b`.

## Key flows
- Photo scan: `Inventory.tsx` -> `POST /ml/analyze-photo` -> Gemini -> editable drafts -> `POST /cases/<id>/items/bulk`. Landing demo: `/ml/demo-analyze-photo` (no login, in-memory, needs consent checkbox).
- Documents: upload -> `POST /documents` -> `POST /documents/<id>/analyze` -> summary, deadlines, coverage.
- Recommendations: `GET/POST /cases/<id>/recommendations` using case tags, inventory and document signals.
- Terms: `GET /terms`, `/terms/status`, `/terms/accept`. Bump `CURRENT_TERMS_VERSION` (backend/app/blueprints/terms.py) and `BUSINESS.legalVersion` together to force re-acceptance.

## Conventions
- Warm, calm product voice; avoid dashes in user-facing copy. Contrast must stay WCAG AA (tokens in `styles.css`).
- Forms use `components/forms/Field`, `PasswordChecklist`, `MissingList`: required marker, inline validation on blur, counters, disabled submit with a visible "what's left" list.
- All Gemini calls go through `generate_with_retry`; untrusted document text goes through `ai_guard`.

## History warning
Commit `ed67c72` ("Initial commit for new repo") merged service modules into one `gemini.py` and deleted routes the frontend uses. The backend was restored from `ed67c72^`. Do not re-flatten without updating every import.

## Open items
- Fill `src/legal/business.ts` (operator name, mailing address, confirm contact mailbox/domain). Have a lawyer review the legal pages.
- Set Supabase Auth password policy to min 8 chars (client checks are not enforcement).
- Plan: more Gemini-driven logic, local/Colab model training (see `ml/`), dataset split leakage and `table_intact` audit before trusting classifier metrics.
- No phone field exists; `lib/validation.ts` has `phoneToE164` ready if one is added.
