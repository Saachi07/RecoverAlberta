# inventory.md: photo inventory without Gemini

Design spec for replacing the Gemini-based room photo inventory in RecoverAlberta (code and repo still say Rebuildr until the rename lands). Status: design only. Nothing here is implemented yet. Read this before touching `backend/app/services/gemini_inventory.py`, `backend/app/blueprints/ml.py`, `backend/app/blueprints/items.py`, `frontend/src/pages/Inventory.tsx`, or anything in `ml/`.

The document side (policies, deadlines, coverage) is a separate spec: see `legal.md`.

Source check: model and dataset facts below were read from the model cards and project pages on 2026-10-21. Anything marked "not verified" was not confirmed in that pass and must be checked before it is relied on. Licenses in particular must be re-read at the time of use.

## 1. Goals and non-goals

Goals
- No third-party AI API in the photo path. Photos of people's homes never leave our servers (later: never leave the phone).
- Models find things (detect, segment, classify). Reviewed tables and rules decide anything that carries claim or legal risk (contents vs building, salvageability).
- Every field carries a calibrated confidence. Low confidence means "please check this", never a guess dressed up as fact.
- Prices come with evidence: comparable products, a date, and whether the number is replacement cost or depreciated (actual cash value).
- Keep today's output shape so the Inventory page, `items/bulk`, and `signals.py` keep working.
- Cover more than fire: smoke, char, water, flood mud, mold, hail dents, wind debris, freeze damage.

Non-goals
- Auto-submitting anything to an insurer. Every line stays user-confirmed. A hallucinated item can look like padding in a claim; a missed item only under-claims.
- Training any model from scratch. We fine-tune pretrained open models.
- Replacing an adjuster or restoration professional. Salvageability is never a promise.

## 2. Current state (what exists today)

Read from the repo (`fixes` branch matches CLAUDE.md).

Live path
- `backend/app/services/gemini_inventory.py`: `analyze_room_photo` downscales to 1568 px on the long side, fixes EXIF rotation, re-encodes JPEG at quality 85, then makes one Gemini call (2.5 Flash, fallback 2.0 Flash, 3 retries with backoff) using a PRE, POST, or AUTO prompt and a strict JSON schema.
- The model returns, per item: name, category (furniture, appliance, electronics, decor, clothing, other), count, condition (new, good, fair, worn, damaged), visible brand, size (small, medium, large), a CAD low/high price estimate, a bounding box, salvageable, salvage note, claim class, claim note. Per room: room type, detected phase (before or after), notes.
- `finalize_analysis` is deterministic Python: fills `claim_class` from a keyword list if the model left it empty, forces salvage to null on before photos, and sums contents-only totals (low and high times count).
- `classify_claim_class` is substring matching. Known weak spots: "outdoor" contains "door", "filing cabinet" matches "cabinet", "hair trimmer" matches "trim". Impact is small because it only runs when the model omits the field, but the taxonomy replaces it anyway.
- Flow: `Inventory.tsx` posts to `/ml/analyze-photo`, the user edits drafts, then `POST /cases/<id>/items/bulk`. Demo route: `/ml/demo-analyze-photo`.

Offline experiment (`ml/`, not wired into the app)
- `yolo_detector.py`: YOLO-World zero-shot counting from text labels. `analyzer.py` still calls Gemini and asks it for a `yolo_label` per item, so the detector depends on Gemini for its vocabulary.
- `classifier/`: ViT-base (`google/vit-base-patch16-224`) fine-tuned for 3 classes (intact, salvageable, destroyed) on chair and table images, labels come from folder names.
- Problems in the classifier pipeline: `build_splits` shuffles every file together, including the `_synthetic` variants of the same source images, so near-duplicates land on both sides of the split. The best checkpoint is picked on the same set it reports. `table_intact` has a TODO about misplaced damaged images. Treat current validation accuracy as untrustworthy.
- `loss_report.py` also uses Gemini for its summary.

Database (`case_items`)
- Columns: name, category, material, estimated_value (one number), damage_type, damage_severity (intact, salvageable, destroyed), confidence, image_url, description, before_url, after_url, receipts, purchase_date. ACV is computed in the app from purchase date and category.
- Implication: price range, comparables, bulk flag, and per-field confidence have no home yet. A migration is part of the rollout.

Storage and privacy
- The `item-images` bucket is public-read behind unguessable URLs (the migration says so and says it can be flipped to signed URLs). Before any training-data collection this must be private and consent-gated.
- Room photos can show faces, mail, medication, and IDs. `signals.py` already derives tags such as medication_visible from item names, so sensitive items do get detected.

## 3. Output contract

Keep the fields the frontend and `items/bulk` already use (section 2). Add, per item:
- `taxonomy_id`: the leaf class from section 5.
- `confidence`: per field (class, condition, price), calibrated.
- `bulk`: true for container-style entries (section 6).
- `damage_types`: list from the damage vocabulary, plus `severity`.
- `price`: low, mid, high; `price_basis` (replacement or ACV); `price_date`; `comparables` (a few products with source and price).
- `evidence`: which photo and which box or mask the item came from.
- `source`: model name and version, rule id, or "user".
Room-level: `coverage_gaps` (parts of the room not photographed) and `merged_from` (which photos were merged).

## 4. Pipeline

1. Capture check: blur, exposure, and coverage. If a photo is unusable, ask for another one before running anything.
2. Room type: scene classifier.
3. Detect and segment: find every item, with a mask, against the taxonomy.
4. Per-item attributes on the crop: subtype, material, size class, wear, built-in vs freestanding, brand and model via OCR and logo matching.
5. Damage: multi-label damage types and severity per item; use the before photo when one exists (section 7).
6. Salvageability: decision table (section 8).
7. Pricing: comparable retrieval plus quantile regression, then depreciation (section 9).
8. Merge across photos: same item seen twice counts once.
9. Claim class: taxonomy lookup plus the built-in head.
10. Calibrate and gate: low-confidence fields are flagged in the UI.

## 5. Taxonomy

This is the main asset. Target 300 to 500 leaf classes eventually; start the first detector with about 120 of the highest-dollar and most common items. Each leaf stores: name, group, contents or building or unclear, bulk flag, typical lifespan (for ACV), price band source, and visual attributes to ask about.

First-draft groups (leaf lists to be filled with an insurance professional and from real photos):

| Group | Examples | Notes |
|---|---|---|
| Seating | sofa, loveseat, armchair, dining chair, office chair, stool | high value, easy to detect |
| Tables | dining, coffee, side, desk, nightstand | |
| Storage furniture | dresser, bookshelf, wardrobe, freestanding cabinet, filing cabinet | built-in cabinets are building |
| Beds | mattress, bed frame, crib | mattress salvage is usually "unlikely" after water |
| Major appliances | fridge, freezer, washer, dryer, range, dishwasher, microwave | built-in vs freestanding matters |
| Small appliances | kettle, toaster, air fryer, vacuum, blender | often bulk |
| Electronics | TV (size class), laptop, monitor, console, soundbar, router | brand and model by OCR |
| Soft goods | area rug, curtains, bedding | wall-to-wall carpet is building |
| Decor | framed art, mirror, floor lamp, table lamp, plants | |
| Kitchenware | dishes, cookware, cutlery | bulk |
| Clothing | closet contents, shoes, coats | bulk |
| Books and media | bookshelf contents | bulk |
| Tools and garage | power tools, workbench, bikes | |
| Outdoor | patio set, BBQ, lawn equipment | |
| Children | stroller, car seat, toys | toys bulk |
| High-value flags | jewelry, instruments, artwork, collectibles | prompt for receipts and appraisals |
| Building items | flooring, built-in cabinets, fixtures, windows, doors | claim class "building" |

Culture and community: include items from non-Western households and Indigenous and religious items. Consult the communities served before the taxonomy is frozen.

## 6. Bulk items

Nobody claims each fork or book individually, and a detector cannot enumerate a bookshelf, a closet, or a cutlery drawer. Add container classes (bookshelf contents, closet contents, kitchen cabinet contents, toy bin) with their own estimators: an estimated count, a category mix, and a price per unit band. Always ask the user to confirm and adjust. Flag bulk entries so totals show their uncertainty.

## 7. Damage and before/after pairs

- Damage vocabulary (multi-label): smoke, soot, char, heat warping, water stain, standing water, flood mud, mold, impact or hail dent, wind debris, freeze or burst damage, none. Severity is ordinal: none, minor, moderate, severe, destroyed.
- The app already stores `before_url` and `after_url`. Comparing the two is much easier than judging damage from one photo. Train a pair model (shared backbone, difference features) for items that have both, and a single-photo model as the fallback.
- Public interior damage data is scarce (section 11). Expect to collect your own.

## 8. Salvageability

Decision table, not a free-running model: material times damage type times severity gives likely, unlikely, or needs professional assessment. Write it with restoration professionals. The models supply the inputs; whenever their confidence is low or the case is not in the table, the answer is "needs professional assessment". The note always advises confirming with the insurer or a restoration professional. Long term, real ground truth is whether cleaning worked, which needs a restoration-company partner.

## 9. Pricing

- Retrieval: embed each item crop with a product-image encoder, retrieve the nearest catalog products, and price from them. Output low, mid, and high through quantile regression over the retrieved prices and item attributes.
- Evidence: show the comparables ("similar to X at $Y") with source and date. This is the inventory equivalent of the document citations in `legal.md`.
- Replacement cost comes from comparables. ACV comes from age and condition through lifespan tables (to be written with an insurance professional). A receipt or purchase date, when the user provides one, overrides the model.
- Currency and region: public product data is mostly US and in USD. Canadian prices need Canadian retailer data, a licensed feed, or a conversion layer with clear labeling. Re-price on a schedule. Consider Statistics Canada consumer price index data by category for ageing old prices.
- The model never invents a price with no basis: if retrieval is weak, return a wide range and flag it.

## 10. Pretrained models to start from

All from the Hugging Face hub or the official repos. License is as stated on the card or repo page on 2026-10-21; re-check before using any in a product.

| Job | Model | Notes (verified unless marked) |
|---|---|---|
| Main detector | `PekingU/rtdetr_r50vd` (RT-DETR) | Apache-2.0, 43M parameters, COCO AP 53.1 (55.3 with Objects365 pretraining), detection only. Supported in Hugging Face transformers. |
| Main detector, alternative | RF-DETR (Roboflow) | The package page for v1.0.7 says code and COCO-pretrained weights are Apache-2.0; a newer release exists, so check the license of each size before using larger variants. Fine-tunes on a COCO-format dataset (train, valid, test folders with `_annotations.coco.json`). The Hugging Face object detection guide fine-tunes `Roboflow/rf-detr-medium`. |
| Pre-labeling (text prompts) | `IDEA-Research/grounding-dino-tiny` | Apache-2.0 per the model card, 52.5 AP zero-shot on COCO per the card. Prompts are lowercase and end with a period; the card's example uses box and text thresholds of 0.4 and 0.3. |
| Pre-labeling, alternative | `google/owlv2-base-patch16-ensemble` | Apache-2.0 per the Hugging Face card. The card says research use is intended and notes web-crawl bias toward well-represented populations. Parameter count and COCO AP (about 155M, 0.434) come from a third-party listing. |
| Masks, tracking | SAM 2 / SAM 2.1 (`facebookresearch/segment-anything-2`) | Apache-2.0 for checkpoints and code per the repo. Sizes 38.9M to 224.4M parameters. Image and video segmentation, automatic mask generation. SAM 3 was not checked. |
| Shared backbone | `facebook/dinov2-base` | Apache-2.0 per the card. Self-supervised features; needs task heads on top. Newer DINO versions may carry a different license (not checked). |
| Image-text embeddings | SigLIP 2 (`google/siglip2-*`) | Apache-2.0 per a third-party listing; confirm on the Hugging Face card. |
| Product retrieval for pricing | `Marqo/marqo-ecommerce-embeddings-L` (and `-B`, smaller) | Apache-2.0, about 652M parameters (L). Product image and text embeddings. The card reports 0.683 MRR on the hard Google Shopping text-to-image task vs 0.574 for ViT-SO400M-14-SigLip. |
| Room type | Places365 CNNs (`CSAILVision/places365`) | Code MIT; pretrained models under CC BY per the repo; 365 scene categories; the dataset license is not stated on the repo page and images belong to their owners. Some Hugging Face room-type classifiers exist (not evaluated; do not use without checking license and data). |
| OCR for labels and model numbers | not yet researched | Candidates to evaluate: PaddleOCR, docTR, Tesseract. Check licenses and accuracy on appliance rating labels. |
| Zero-shot counting (current `ml/`) | YOLO-World via Ultralytics | Ultralytics YOLO is AGPL as far as I know (not verified in this pass). Decide before building on it. |

Suggested stack: RT-DETR or RF-DETR as the detector, SAM 2 for masks, DINOv2 as the attribute backbone, Marqo or SigLIP 2 for comparables, Grounding DINO or OWLv2 only to pre-label photos for humans to correct (they never run in production).

## 11. Data sources

Public, verified 2026-10-21. Check license again at the time of use.

| Source | What it gives | Size and license notes |
|---|---|---|
| LVIS | long-tail instance segmentation labels on COCO images | 1,203 categories, about 160k images, about 2M annotations (boxes and masks). License not stated on the page I read; COCO images carry their own terms (not verified). |
| Open Images V7 | broad boxes, masks, labels | about 9M images, over 20,000 image-level categories, 1.9M densely annotated images (average 8.3 boxes and 1.5 masks per image). License not confirmed on the pages I read; check the Open Images site. |
| ADE20K | indoor scenes with object and part segmentation, scene categories | 25,574 train and 2,000 validation images. Requires registration and agreement to its Terms of Use; whether commercial use is allowed is not stated on the page. |
| Amazon Berkeley Objects (ABO) | product catalog images, metadata, 3D models | 147,702 products, 398,212 catalog images, over 7,900 3D models with masks, depth, and 91 rendered viewpoints each. The ABO site states CC BY 4.0 with attribution to Amazon.com. Good for product retrieval and synthetic training. |
| Amazon Reviews 2023 | item metadata including price (USD at crawl time), images, categories | 48.19M items across 33 categories (Home_and_Kitchen, Appliances, Electronics, and more), 750 GB total. The dataset card states no license or usage terms: do not assume commercial rights. Prices are US retail. |
| Roboflow Universe "House Damage 2" | 2,953 images, 27 classes across eight damage types (fire, water, mold, cracks, collapses, earthquake, tornado) with severity variants | CC BY 4.0. The page does not say whether images are interior or exterior. Quality unknown; audit before use. |
| IDFire (IEEE DataPort) | 1,015 indoor images with instance segmentation of combustible items in five room types | Not damage data. Needs an IEEE DataPort subscription; license not stated. Useful for indoor item segmentation. |
| Hugging Face hub search | no ready-made labeled interior fire or flood damage set turned up | Only wildfire scar and forest fire sets appeared. Assume interior damage data must be collected. |
| Objects365 | pretraining data referenced by RT-DETR variants | Not verified; check access and license before using. |

Own data (the real bottleneck)
- Photographed rooms and items collected by the team and volunteers, staged and real, with consent.
- Restoration companies and relief organizations. Examples worth approaching (no data-sharing confirmed): Canadian restoration firms with Alberta disaster response history and the Canadian Red Cross, which has a national partnership with a restoration company.
- Fire-department training burns and houses slated for demolition, as sources of real damage (ask; not confirmed to be available).
- User-donated photos from the app: opt-in only, private storage, de-identified, with a clear way to withdraw.
- Synthetic data: render rooms from 3D assets (ABO) and simulate damage. Use for pretraining and rare classes only; the test set stays 100 percent real.

Rough size guesses (not benchmarks): thousands of labeled room photos for the detector, and hundreds to low thousands of labeled crops per damage type and material group.

## 12. Labeling with CVAT and Label Studio

Why self-host: photos of homes are sensitive, so run both tools on your own hardware, behind login, with annotators under an agreement.

Which tool for what (my recommendation)
- CVAT: boxes, polygons, masks, and video. Best for the detection and segmentation work.
- Label Studio: classification-style tasks and review (damage type and severity on a crop, comparable-product match checking, attribute questions) and anything mixed with text.

CVAT workflow (from the CVAT docs)
1. Install self-hosted CVAT. Create a project with your taxonomy as labels, and add attributes (for example contents or building, built-in, condition).
2. Create tasks in batches (a few hundred photos each) and upload.
3. Pre-label: Tasks, Action, Automatic annotation. Choose a detector, map its labels to your task labels (each model only knows its own labels), set a confidence threshold, optionally set a region of interest, then Annotate. Use a low threshold so humans reject false positives instead of drawing missed boxes.
4. Add your own model: an administrator deploys a Docker-based Nuclio function next to CVAT, or you run a native AI agent function on your own hardware with Docker Compose (the SAM 2 agent directory is the documented example; configure its `.env` with the CVAT URL, access token, and function name, run `docker compose up`, then check the Models page). Third-party models served by Hugging Face or Roboflow are listed for Enterprise and Online only. The SAM 2 tracker is Nuclio (Enterprise) or an AI agent (Online and Enterprise). Check which of these your edition supports.
5. Use the AI assistance tools to make masks from points or boxes. Annotators correct instead of drawing from scratch.
6. Review pass by a second person; keep a gold set that is never trained on.
7. Export for training. CVAT supports COCO and YOLO among its formats (confirm the current list and mask support in the docs).

Label Studio workflow (from the Label Studio material)
1. `pip install label-studio`, then `label-studio start` (UI on localhost:8080), or use Docker Compose for something sturdier.
2. Create a project with a `RectangleLabels` config tied to an `Image` tag (the image comes from `$image`), listing your labels. Import tasks as images or connect S3 storage.
3. Optional pre-annotations: clone `label-studio-ml-backend`, use the YOLO example, set `LABEL_STUDIO_URL` and an API token in its `docker-compose.yml` (use `host.docker.internal` for a local Label Studio), run `docker compose up --build`, then in project Settings, Model, connect the backend. The labels in `predicted_values` must match the model's class names exactly. Annotators then correct the predictions.
4. Multiple annotators: setting an overlap percentage (for example 20) has that share of tasks labeled by more than one person, which lets you measure agreement yourself (Label Studio does not compute it for you in the material I read). Task assignment and review queues are Enterprise and Starter Cloud features.
5. Export JSON, CSV, or COCO.

Labeling guidelines (write these before scaling)
- One written definition per taxonomy class with example and counter-example photos.
- Rules for occluded items, partial items, reflections in mirrors (do not label), photos on walls (frames yes, content no), and containers (bulk class, not every item).
- Pilot on 100 photos with two annotators, measure agreement, fix the guidelines, then scale.
- Never train on the gold set. Re-audit labels after each model round by looking at confidently wrong predictions.

## 13. Training recipe

1. Pretrain wide, fine-tune narrow: start from a COCO or Objects365-pretrained detector, mapped to your taxonomy, then fine-tune on your own labeled home photos. Use sampling that favors rare classes.
2. Training loop, as in the Hugging Face object detection guide: COCO-style annotations (absolute pixel boxes, category ids), a model loaded with the new label set and mismatched head sizes ignored, augmentation on the training split only (flip, brightness and contrast, hue, small perspective), evaluation by COCO-style mAP, best checkpoint chosen by mAP on the validation split. The guide's example (RF-DETR medium, about 6.7k training images, 5 epochs) took about 35 to 40 minutes on one A100; budget more for a real taxonomy.
3. Attribute and damage heads: shared self-supervised backbone, separate heads per attribute, loss weights tuned per head, backbone frozen first then partly unfrozen.
4. Calibrate (temperature scaling) and pick abstain thresholds per field on the validation split.
5. Mine hard examples and low-confidence predictions for the next labeling round (active learning).
6. Distill the detector to a small model later so it can run on the phone (offline during an emergency, and photos never upload).
7. Compute is the easy part; labeling and partnerships take the time.

## 14. Evaluation

- Split by household and room, never by photo. Keep synthetic variants and near-duplicates with their originals. Run near-duplicate detection (perceptual hash or embedding similarity) across the whole pool before splitting.
- Three sets: train, validation (tuning and checkpoint choice), test (touched once per release).
- Metrics: item recall and precision, count error, price interval coverage, damage macro-F1, calibration error, abstain rate.
- Slices: apartment vs house, rural, dark rooms, clutter, cheap phone cameras, culturally specific items.
- Error cost: false items hurt more than missed items; tune precision for items that go into the claim total.
- One-time baseline: compare against the current Gemini output on the held-out set before retiring it. Not a runtime dependency.

## 15. Fixing the existing classifier (do first)

1. Group images by source (a synthetic variant stays with its original) and by scene where known, then split by group with a fixed seed: train, validation, test.
2. Run near-duplicate detection across the whole pool first.
3. Audit `table_intact`: review the flagged filenames by hand, then train once and inspect the confidently wrong predictions for more mislabels.
4. Report per-class precision and recall, the confusion matrix, and calibration on the held-out test set, once.
5. Record label provenance (original, synthetic, source) in a manifest instead of folder names.
6. Treat the old 3-class labels as a starting point: the new vocabulary is multi-label damage plus ordinal severity.

## 16. Privacy and consent

- Make `item-images` private and serve signed URLs before collecting any training data.
- Opt-in consent for using photos in training, separate from the terms of use, with a way to withdraw and delete.
- De-identify: blur faces, photos on walls, mail, IDs, and visible medication before a photo enters a training set.
- Annotation tools self-hosted; annotators under an agreement; no photos on personal devices.
- Retention: a stated period, and delete derived training copies on withdrawal.
- Check with a lawyer (the same review that `legal.md` and CLAUDE.md call for) before launch.

## 17. Rollout and fallback

- Feature-flag the pipeline. `ml.py` picks the path.
- Fallback chain: own models, then user manual entry. If neither is available, the existing flow remains until the flag is retired.
- Build order:
  1. Foundations: section 15, test set, taxonomy v1, private bucket, consent flow.
  2. Detector for the top 120 items (furniture, appliances, electronics), measured against the Gemini baseline once.
  3. Attributes, claim class by taxonomy, and comparables pricing (new columns for range and evidence).
  4. Damage and salvage, widened to water, hail, and wind.
  5. Multi-photo merge, capture guidance, bulk-item estimators.
  6. On-device distillation and the correction flywheel.
- Quick fixes that do not need the rebuild: replace the keyword claim-class fallback with a lookup, make the bucket private, store the price range.

## 18. What you give up

Gemini recognizes the weird long tail and reads text in the wild with no labels. Own models are strong on the taxonomy and weaker on the unexpected. Mitigation: an "unrecognized item" path where the user types a name, a catch-all class, and fast taxonomy growth from corrections.

## 19. Open questions

- Is an open-weight vision-language model allowed anywhere (annotation help only), or is "no Gemini" meant as "no pretrained generative model"?
- Which detector license is acceptable (Apache-2.0 detectors vs AGPL YOLO)?
- Where does price data come from for Canada, and is retailer data licensable?
- Which restoration company, relief organization, or fire service will share real damage photos?
- Who annotates, at what budget, and where are the tools hosted?
- OCR choice and license.
- Are Amazon Reviews 2023, LVIS, Open Images, and ADE20K usable commercially? Read the terms before use.

## 20. Decisions log

- 2026-10-21: Direction is no Gemini for the photo inventory; models find things, reviewed tables decide risky ones.
- 2026-10-21: Stack to evaluate first: RT-DETR or RF-DETR, SAM 2, DINOv2, Marqo or SigLIP 2; Grounding DINO or OWLv2 for pre-labeling only.
- 2026-10-21: CVAT for boxes and masks, Label Studio for classification and review, both self-hosted.
- 2026-10-21: Fix the classifier split and audit `table_intact` before any new training.