# legal.md: document analysis without Gemini

Design spec for replacing the Gemini-based insurance and legal document analysis in RecoverAlberta (code and repo still say Rebuildr until the rename lands). Status: design only. Nothing here is implemented yet. Read this before touching `backend/app/services/gemini_documents.py`, `backend/app/services/document_pipeline.py`, `backend/app/services/signals.py`, or anything in `pdf_and_summary/`.

The inventory side (photo scan, pricing, damage) is a separate design and is not covered here.

## 1. Goals and non-goals

Goals
- No third-party AI API in the document path. Documents never leave our servers.
- Models find things (classify, extract, tag). Hand-written, reviewed text explains them. Generated text is limited and always checked against the source.
- Every output carries a source location in the original PDF and a confidence. When unsure, say so and show the original text.
- Keep today's JSON output shape so the frontend and `signals.py` keep working.
- Cover more than fire: hail, wind, overland flood, sewer backup, freezing, power outage and food spoilage clauses.

Non-goals
- Giving legal advice. Wording is always "your policy says", never "you are covered".
- Replacing a broker, adjuster, or lawyer.
- Training any model from scratch. We fine-tune pretrained open models.

## 2. Current state (what exists today)

Read from the repo; details of `gemini_documents` come from the same code that main has as one flattened `gemini.py`.

- Stage 1, classifier: `gemini_documents.analyze_document` sends the raw PDF or image to Gemini. Returns doc_type, title, summary, key_fields. Has an "other" bucket for non-recovery documents.
- Stage 2, rich analysis: `document_pipeline.analyze_document_rich` calls `pdf_and_summary.process_pdf` with OCR off, spaCy on, PII redaction on. Order inside `pdf_and_summary/pipeline.py`: PyMuPDF text per page, spaCy entities, redact, add `[PAGE n]` markers, Gemini summary (REST, temperature 0, JSON schema), `ai_guard` post-check, quote verification, rehydrate placeholders.
- Photos of documents: `gemini_documents.analyze_image_rich` runs the same schema on the image. Quotes cannot be verified, so `verification.checked` is false.
- Local fallback: `summarizer._local_summary` (regex and spaCy) when no API key is set.
- Verification: `pdf_and_summary/verification.py`, exact substring match after whitespace and case normalization.
- Consumers: `signals.py` reads the persisted analysis for insurer name, deadlines, and denial signals; the recommender uses them.
- Known gaps: scanned PDFs hit "no text" because OCR is off; verification is brittle to smart quotes and hyphenation; the summarizer has its own urllib retry and a different default model than the rest of the Gemini calls (CLAUDE.md says all calls use `generate_with_retry`, which is not true for the summarizer); redaction depends on `en_core_web_sm` for names, and the stage 1 classifier sees unredacted bytes.

## 3. Output contract

Keep the fields the frontend already renders: plain_language_summary, deadlines, flagged_issues, coverage_limits, coverage_scope, deductible, glossary, required_actions, warnings, verification, nlp block, extraction_meta. `document_pipeline._shape` stays the single place that shapes the result.

Add per item:
- `evidence`: page number plus character offsets (and a page region when available) in the original text.
- `confidence`: calibrated probability from the model that produced the item.
- For deadlines: `verbatim` (the text as written), `resolved_date` (computed), `assumption` (what the date was computed from), and `rule` (which parsing rule fired).
- `source`: which component produced the item (model name and version, template id, or rule id).

## 4. Pipeline

1. Ingest
   - Native PDF text via PyMuPDF, per page.
   - Scans and photos: turn real OCR on, plus layout analysis (reading order, headings, tables, key-value blocks, headers and footers). Scanned PDFs stop being a dead end.
   - Keep character offsets through every later step so evidence can point back.
2. Classify the document
   - Fine-tuned text and layout classifier. Classes: insurance policy, declarations page, endorsement, claim form, claim letter, denial letter, estimate, invoice, receipt, ID, deed, correspondence, not a recovery document.
   - Explicit reject class plus an out-of-distribution score so odd documents are not forced into the nearest class.
3. Segment
   - Split into sections: declarations, definitions, insuring agreement, exclusions, conditions, endorsements.
   - Use headings and font cues as features. Falls back to "unsegmented" when structure is unclear.
4. Tag spans with roles
   - Token classifier over sliding windows with overlap (documents are long).
   - Roles: DATE as deadline, issue date, effective date, expiry, or date of loss; MONEY as limit, sublimit, deductible, premium, or amount claimed; parties as insurer, insured, adjuster, broker; policy and claim numbers; addresses; named perils.
5. Classify clause roles
   - Sentence or clause classifier: grant, exclusion, exception to an exclusion, condition, definition, limit, sublimit.
6. Resolve deadlines (section 5)
7. Compose coverage (section 6)
8. Detect issues with rules (section 7)
9. Write plain language (section 8)
10. Assemble the output and attach evidence and confidence

## 5. Deadline engine

The tagger finds the obligation and its time phrase. A deterministic resolver turns it into a date. This is the highest-value piece, so it gets the most care.

- Absolute dates parse directly.
- Relative durations ("within 60 days of the loss") anchor to a known event: date of loss (from the case), date on the letter, policy effective date.
- Unknown anchors ("after receipt of this letter"): show an earliest and latest range and use the earliest plausible date. Being early costs nothing, being late can.
- Vague phrases ("promptly", "as soon as practicable"): no computed date, flag as act now.
- Calendar vs business days: follow the wording when stated; when not stated, assume calendar days.
- Never adjust for weekends or holidays. Say that no adjustment was made and tell the user to confirm with the insurer.
- Always store both `verbatim` and `resolved_date`, and show the assumption in the UI.
- Output feeds `signals.py` (deadline_within_7d, deadline_within_30d, denial_received).

## 6. Coverage composer

Policies are layered, so do not ask a model "is flood covered?". Extract clauses with roles (step 5), then compose them with plain logic:

- covered if there is a grant and no exclusion
- covered if excluded but an exception to that exclusion applies
- endorsements take precedence over the base policy
- sublimits and conditions attach to the peril they name
- anything the logic cannot resolve returns "conditional" or "unclear" and shows the clauses

Perils to support first: fire, smoke, wildfire, water damage, overland flood, sewer backup, hail, wind, freezing and ice, theft, additional living expenses, power outage and food spoilage. Add perils by adding labels and examples, not new code paths.

Deductible handling matters more as we widen past fire: capture fixed vs percentage, what the percentage applies to, and whether a separate deductible exists for a peril (for example hail or wind). Verify real wording against actual Alberta policies; do not assume.

## 6a. Models

Start from pretrained encoders and fine-tune. Continue pretraining on unlabeled insurance wordings first (domain-adaptive pretraining); it helps a lot when labels are scarce. Calibrate outputs (temperature scaling) so confidences mean something. Check the license of every model before using it commercially; some layout-aware models are non-commercial, and some detector and OCR packages carry restrictive licenses.

| Task | Approach | Main risk |
|---|---|---|
| Doc type and reject class | fine-tuned classifier | odd documents confidently misfiled |
| Section segmentation | heading and font features plus classifier | unusual structure |
| Span tagging | token classifier, sliding windows | long documents, clauses split across windows |
| Clause roles | sentence classifier | exceptions buried in long sentences |
| Tables | rules plus learned table detector | declarations pages vary a lot |
| PII | fine-tuned NER, trained on Canadian names and addresses | non-Anglo names missed by small models |

## 7. Rule layer (Alberta and general)

Deterministic detectors that run on the extracted fields and raise flagged issues. Examples to start with: short proof-of-loss windows, actual cash value vs replacement cost, depreciation holdback, percentage deductibles, vacancy conditions, coinsurance, sublimits on high-value items, additional living expense caps. Each rule has an id, a plain-language message, and a link to the clause that triggered it.

A lawyer or licensed insurance professional must review this rule layer and the templates before launch. Do not encode statutes or limitation periods from memory.

## 8. Plain language, in tiers

1. Reviewed templates and a curated glossary (about 200 terms). This is the default. Every extracted field renders through a template, for example "Your deductible is $X. This is the amount you pay before your insurance pays." No generation, so no hallucination.
2. Optional clause rewriting with a small seq2seq model trained on human-written clause-to-plain pairs. Before showing any rewrite, require all of:
   - every number, date, and name in the rewrite appears in the source clause
   - an entailment model agrees the rewrite follows from the clause
   If any check fails, fall back to tier 1 or show the original wording.
3. Measure reading level automatically. Target grade 8 or below, as today.

The summary at the top is assembled from extracted facts with templates, ordered by urgency (deadlines first).

## 9. Citations and verification

Extraction is extractive, so every item has offsets and a page region. The UI highlights the original PDF instead of showing a model-written quote. This replaces the substring check in `verification.py` for extracted items. For any generated rewrite, the faithfulness checks in section 8 apply instead.

## 10. Redaction and security

- We no longer need redaction to protect users from a third-party API. We still need it for building training data and for logs and exports.
- Train a proper PII NER on Canadian names and addresses. Test on non-Anglo and Indigenous names specifically, since small spaCy models miss them.
- Extractive models do not follow instructions, so prompt injection stops being an attack on the extraction path. `ai_guard` only stays relevant for any generative component we keep.
- Keep `upload_validation` and `rate_limit` as they are.

## 11. Data and annotation

Corpus
- Public policy wordings from insurers, as unlabeled text for pretraining (rough guess: a few thousand).
- A few hundred documents fully annotated (rough guess, not a benchmark).
- Documents donated by users, only with explicit consent and after de-identification.
- Synthetic documents in varied layouts to widen coverage.
- Include wordings for hail, wind, overland flood, sewer backup, and freezing.

Annotation layers
1. Document type
2. Section
3. Spans with roles
4. Clause roles
5. Coverage status per peril

Process
- Write guidelines with someone who knows insurance, ideally a broker. Pilot on a small set.
- Two annotators label an overlap set; measure agreement before scaling.
- Use active learning to pick what to label next.
- Keep a locked gold set that is never used for training.

## 12. Evaluation

- Weight errors by harm. A missed or wrong deadline is far worse than a missed glossary term. Tune deadline extraction for recall, and review every deadline miss by hand.
- Hold out whole insurers and templates (leave-one-insurer-out) to test unseen formats. Never split pages of one document across train and test.
- Measure abstention quality: does it say "I could not find a deductible" instead of guessing?
- Per-field precision and recall, calibration error, and reading level.
- Optional: compare against the current Gemini output on the gold set before retiring it. This is a one-time baseline, not a runtime dependency.

## 13. Rollout and fallback

- Put the new pipeline behind a flag. `document_pipeline` picks the path.
- Fallback chain: own models, then the existing local regex and spaCy summary, then the original document with highlights and no summary.
- Build order:
  1. Classifier, then deadlines, limits, and deductible (smallest scope, highest value per label)
  2. Coverage scope and clause roles
  3. Plain-language templates, glossary, and rewrite checks
  4. Scans, layout, tables, and photo documents
  5. PII NER and training-data tooling
- Quick fixes that do not depend on the rebuild and can be done now: smart-quote and hyphenation tolerance in `verification.py`, route scanned PDFs through OCR or the image path, update CLAUDE.md where it has drifted (summarizer retry and model).

## 14. Open questions

- Is an open-weight language model allowed anywhere (annotation helper or rewrite tier), or is "no Gemini" meant as "no pretrained generative model at all"?
- Where does the annotated corpus live, and who can see donated documents?
- What does the consent flow for donated documents look like?
- Who reviews templates, glossary, and the Alberta rule layer, and how often?
- Which model licenses are acceptable for a product?

## 15. Decisions log

- 2026-10-21: App renamed to RecoverAlberta (code still says Rebuildr). HomeProof rejected as too narrow and already in use.
- 2026-10-21: Direction is no Gemini for documents; models find things, reviewed templates explain them.
- 2026-10-21: Deadline engine, coverage composer, and PDF highlighting are the three ideas to protect.