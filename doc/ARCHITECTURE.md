# GeoVigil Analytics — System Architecture

> Clandestine airstrip detection platform for Peru  
> UNODC / GeoVigil Analytics Project

---

## Overview

GeoVigil Analytics is a satellite-imagery-based detection system that identifies clandestine airstrips in Peru using YOLO object detection models. Detection results are published to a web dashboard via an automated daily pipeline.

```
Satellite Imagery (Sentinel-2 + Sentinel-1 + Planet NICFI) / GFW Alerts API
        │
        ▼
  Workstation (Windows, shared PC)
  ├─ Weekly cron via Task Scheduler
  ├─ NICFI: YOLO inference (shape-based, confirming)
  ├─ Sentinel-2: change-detection logic (non-ML, trigger only)
  │    └─ Sentinel-1 backscatter: additional feature for Sentinel-2 calibration (not an independent source)
  ├─ GFW: Integrated Deforestation Alerts (GLAD-L/GLAD-S2/RADD), trigger only
  ├─ Merge by dominance rule (NICFI confirmation always wins; no WBF/score-blending)
  └─ git push → data/detections.json
        │
        ▼
  GitHub Repository (main branch)
        │
        ▼
  Cloudflare Pages (auto-deploy)
        │
        ▼
  Web Dashboard (Vanilla JS + Leaflet)
```

---

## Satellite Imagery Sources

Three sources feed the pipeline: two early-warning trigger sources (Sentinel-2, GFW) that run in parallel, plus the NICFI confirming source. Sentinel-1 is not an independent source — see "Sentinel-1 as a Sentinel-2 feature" below.

### Source 1 — Sentinel-2 (ESA Copernicus)

| Property | Value |
|---|---|
| Resolution | 10 m (visible bands) |
| Update cadence | Every 5 days (raw imagery) |
| Cloud coverage | Affected by clouds — filtered at < 20% cloud cover |
| Cost | Free, open data |
| Access | Copernicus Data Space API / `sentinelsat` / `eodag` Python library |

### Source 2 — Planet NICFI (Free Tier)

| Property | Value |
|---|---|
| Resolution | 4.77 m |
| Update cadence | Monthly cloud-free mosaic |
| Cloud coverage | Not affected — pre-composited mosaic |
| Cost | Free (NICFI Level 1, Norway-funded) |
| Access | Google Earth Engine Python API |
| Geographic coverage | Tropical forests including all of Peru |

### Source 3 — Global Forest Watch (GFW) Integrated Deforestation Alerts

A second early-warning trigger source, run in parallel with Sentinel-2 (confirmed 2026-07-01 — see [CONCEPT_NOTE.md](CONCEPT_NOTE.md) "Global Forest Watch（GFW）連携と付加特徴量"). GFW's Integrated Deforestation Alerts blend three sub-systems with differing resolution/cadence, none of which are unified:

| Sub-system | Underlying satellite | Resolution | Update cadence |
|---|---|---|---|
| GLAD-L | Landsat (optical) | 30 m | Weekly |
| GLAD-S2 | Sentinel-2 (optical) | 10 m | Weekly (cloud-affected) |
| RADD | Sentinel-1 (SAR) | 10 m | Near-real-time (cloud-independent; 6–12 day gap-free coverage in the tropics) |

| Property | Value |
|---|---|
| Cost | Free, open data |
| Access | GFW API (generic client module — reused by future features, e.g. Coca Crop prediction) |
| Role | Early warning only, same as Sentinel-2 — **cannot confirm/upgrade to `active`** |

Each GFW alert retains a tag for which sub-system produced it, since resolution/freshness differs; this tag is a candidate calibration-curve feature. GFW's own alert confidence level (low/nominal/high) is used to fit a **GFW-specific calibration curve**, separate from Sentinel-2's NDVI-margin curve (the two are not directly comparable — see CONCEPT_NOTE.md).

**Why not build a custom Sentinel-1 (SAR) detection layer instead of using RADD as-is:** RADD's real-world update advantage over clear-sky Sentinel-2 (5 days) is modest, and SAR speckle-noise/terrain-distortion processing is more specialized than optical NDVI change detection. A custom Sentinel-1 shape-filter layer remains a possible future enhancement (multi-year re-training-cycle candidate) but is out of scope for now.

### Sentinel-1 as a Sentinel-2 calibration feature (not an independent source)

Runways are smooth bare ground, which backscatters weakly (dark) in SAR imagery. This characteristic is captured as an **additional feature on Sentinel-2 change-detection candidates**, not as a separate detection source or model:

- For each Sentinel-2 candidate point/date, the corresponding Sentinel-1 backscatter value (magnitude of backscatter drop) is fetched
- Once step-2 staff labels are available, tested statistically for whether it improves predictive power over the NDVI margin alone
- If correlated: folded into the same logistic-regression framework used for the Sentinel-2×GFW boost (`P(TP | Sentinel-2 margin, SAR feature)`)
- If not correlated: retained as metadata only, same treatment as slope/river-distance data (see CONCEPT_NOTE.md)

### Rationale for using multiple sources

| Scenario | Source used | Frequency |
|---|---|---|
| Clear sky over target area | Sentinel-2 (± Sentinel-1 feature) | Up to weekly |
| Cloud cover / needs cross-check | GFW (GLAD-L/GLAD-S2/RADD) | Weekly (RADD near-real-time) |
| Heavy cloud cover, shape confirmation needed | Planet NICFI mosaic | Monthly (guaranteed) |
| Sentinel-2 and GFW both flag same location | Both — statistical confidence boost if justified (no arbitrary blending) | Weekly / monthly |

Using multiple early-warning sources plus a monthly guaranteed confirming source ensures that every target area receives at least one detection update per month regardless of cloud conditions, while clear-sky areas can be updated more frequently via Sentinel-2/GFW.

---

## Machine Learning Pipeline

> **Revised 2026-06-30** — see [CONCEPT_NOTE.md](CONCEPT_NOTE.md) for the reasoning behind this revision. The original two-independent-model + WBF design (kept below for history) has been replaced by a single confirming model (NICFI) plus a change-detection early-warning layer (Sentinel-2).

### Models (current design)

| Component | Imagery | Role | Confirms `active`? |
|---|---|---|---|
| `model_planet.pt` (YOLO) | Planet NICFI tiles | Main detection — shape-based object detection | Yes — only source that can confirm/upgrade to `active` |
| Change-detection logic (non-ML or lightweight) | Sentinel-2 tiles (+ Sentinel-1 backscatter feature, if correlation confirmed) | Early warning — flags vegetation-clearing changes, no shape classification | No — only produces `unconfirmed` entries |
| GFW alert ingestion (non-ML) | GFW Integrated Deforestation Alerts (GLAD-L/GLAD-S2/RADD) | Early warning — second, independent trigger source, no shape classification | No — only produces `unconfirmed` entries, same tier as Sentinel-2 |

**Why Sentinel-2 has no independent YOLO model:** at 10 m resolution, a runway (15–30 m wide) spans only 1–3 pixels — too coarse for reliable shape-based classification. Sentinel-2's value is update frequency (weekly, clear-sky permitting), not shape discrimination. It is used as a trigger, not a confirmer. The same reasoning applies to GFW (10–30 m depending on sub-system).

**Sentinel-2 and GFW each have their own calibration curve — not a shared one.** Sentinel-2's continuous "margin" feature (primarily NDVI change magnitude relative to the decision threshold) is mapped to an empirical true-positive probability via a monotonic calibration curve (isotonic regression, fit against staff-verification batches — see [CONCEPT_NOTE.md](CONCEPT_NOTE.md) "構築フロー"). GFW provides a different, ordinal feature (its own alert confidence level: low/nominal/high, plus which sub-system fired), so a **separate GFW calibration curve** is fit rather than reusing Sentinel-2's — the two features are not on the same scale. If the Sentinel-1 backscatter feature is confirmed to add predictive power (see "Sentinel-1 as a Sentinel-2 calibration feature" above), it is folded into the Sentinel-2 model as an added regressor, not a separate curve.

**Sentinel-2 × GFW co-detection confidence boost:** unlike the NICFI×Sentinel-2 "corroboration boost" (rejected — see below), a boost when both non-confirming sources independently flag the same location *can* be justified here, because both scores are on the true-positive-probability scale already: `P(TP | Sentinel-2 margin, GFW feature)` is estimated via logistic regression once co-detection staff labels are available (CONCEPT_NOTE.md step 2b/2c). Only adopted if the fit is statistically justified — not an arbitrary fixed increment.

### Combining NICFI, Sentinel-2, and GFW confidence — no WBF, no score-blending (confirmed)

**Decided: WBF is not used, and confidences are never numerically fused (no weighted average) between NICFI and the early-warning sources.** The original rationale for WBF (merging two independent models' bounding boxes via IoU) assumed two YOLO models running in parallel with comparable, box-level scores. Under the revised design, neither Sentinel-2 nor GFW produces bounding boxes at all (point + score output only), so IoU-based fusion cannot apply mechanically. But beyond that: even the underlying idea of averaging NICFI's confidence with an early-warning score is rejected, because the scores measure different things (NICFI = shape-classification confidence; Sentinel-2/GFW = "is this change airstrip-like" proxy score with a much lower ceiling, since neither can resolve shape at their resolution) and the sources are not peers in the state machine — only NICFI can confirm/upgrade to `active`. (The Sentinel-2×GFW boost above is a different case: both are early-warning peers, so combining them is a same-tier calibration exercise, not a cross-tier WBF-style fusion.)

**Dominance rule (confirmed):** `confidence` is not derived from the current `status` — it is the score attached to the **most recent update event**, subject to dominance on write:
- A NICFI detection **always** overwrites `confidence`/`source` with its own YOLO score, regardless of what was there before.
- A Sentinel-2 or GFW detection overwrites `confidence`/`source` with its own calibrated score (or the statistically justified Sentinel-2×GFW combined score, if both fire on the same candidate) **only if the record's current `source` is not `"Planet NICFI"`** (i.e., an early-warning detection may update an early-warning-only record, but may never overwrite a NICFI-confirmed value).
- If no new detection arrives, `confidence`/`source` simply retain their last value — including through a `status` transition from `active` to `unconfirmed` (e.g., a NICFI-confirmed record aging past 3 months without reconfirmation still shows NICFI's last score, not a blank or early-warning-derived value).
- A NICFI×early-warning "corroboration boost" (small confidence increase when NICFI and an early-warning source both flag the same location) was considered and **rejected** — the boost magnitude would be arbitrary without a proper probabilistic model, and adds complexity for unclear benefit. Not implemented. (This is distinct from the Sentinel-2×GFW boost described above, which is same-tier and statistically estimable.)

<details>
<summary>Original design (superseded, kept for reference)</summary>

Two separate YOLO models were originally planned:

| Model | Training imagery | Status |
|---|---|---|
| `model_planet.pt` | Planet NICFI tiles | To be trained / inherited from predecessor |
| `model_sentinel.pt` | Sentinel-2 tiles | To be trained / inherited from predecessor |

When detections from both models were available for the same geographic area, results would be merged using **Weighted Boxes Fusion (WBF)**:

```python
from ensemble_boxes import weighted_boxes_fusion

boxes, scores, labels = weighted_boxes_fusion(
    [boxes_nicfi, boxes_sentinel],
    [scores_nicfi, scores_sentinel],
    [labels_nicfi, labels_sentinel],
    iou_thr=0.5,
    skip_box_thr=0.4,
)
```

</details>

---

## Pipeline Execution (Workstation)

### Directory structure

```
py/
  pipeline/
    fetch_sentinel2.py    # Sentinel-2 imagery retrieval (Copernicus Data Space)
    fetch_sentinel1.py    # Sentinel-1 backscatter retrieval (feature for Sentinel-2 candidates only)
    fetch_planet.py       # Planet NICFI monthly mosaic retrieval
    fetch_gfw.py          # GFW Integrated Deforestation Alerts client (generic, reusable by future features)
    run_inference.py      # YOLO inference (NICFI only)
    change_detection.py   # Sentinel-2 NDVI change-detection + shape filters (non-ML) + Sentinel-1 feature attachment
    merge.py              # Dominance-rule merge (NICFI confirmation wins; Sentinel-2×GFW same-tier boost if justified; no WBF/score-blending)
    update_json.py        # Update detections.json (dedup + status management)
    git_push.py           # Commit and push to GitHub
  daily_run.py            # Entry point called by Task Scheduler
web/
  data/
    detections.json      # Output consumed by the web dashboard
```

### Execution schedule

- **Trigger:** Windows Task Scheduler, weekly (e.g., every Monday 02:00 local time)
- **Steps:**
  1. Fetch latest Sentinel-2 imagery for target regions (skip if cloud cover > 20%); fetch Sentinel-1 backscatter for any Sentinel-2 candidates found
  2. Fetch latest GFW alerts for the same period
  3. Fetch latest Planet NICFI mosaic if a new monthly mosaic is available
  4. Run NICFI YOLO inference and/or Sentinel-2 change detection and/or GFW alert ingestion on available imagery/data
  5. Merge results using the dominance rule (see Models section) — NICFI always wins; Sentinel-2×GFW combined only if statistically justified; no WBF, no score-blending
  6. Write `data/detections.json`
  7. `git commit` + `git push` to `main` branch

### GitHub authentication on the workstation

A **repository-scoped Deploy Key** (SSH) or **Fine-grained Personal Access Token** limited to this repository with `contents: write` permission is used. This avoids storing full-account credentials on a shared machine.

---

## Output Format — `data/detections.json`

```json
{
  "generated_at": "2026-06-22T02:00:00Z",
  "is_demo": false,
  "detections": [
    {
      "lat": -3.7491,
      "lon": -73.2538,
      "confidence": 0.93,
      "detected_at": "2026-01-10 08:22",
      "confirmed_at": "2026-06-22 02:15",
      "status": "active",
      "source": "Planet NICFI"
    }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `generated_at` | ISO 8601 string | Pipeline execution timestamp |
| `is_demo` | boolean | `true` for demo/test data, `false` for real detections |
| `lat` / `lon` | float | WGS84 coordinates of detected airstrip centroid |
| `confidence` | float (0–1) | Confidence of the currently-dominant source only — see "Combining NICFI, Sentinel-2, and GFW confidence" above. Not a cross-tier blended/ensembled value; `"active"` records show NICFI's YOLO score, `"unconfirmed"` records show Sentinel-2's calibrated score, GFW's calibrated score, or the statistically justified Sentinel-2×GFW combined score if both fired |
| `detected_at` | string | Timestamp of first detection |
| `confirmed_at` | string | Timestamp of most recent detection (updated each pipeline run) |
| `status` | string | See lifecycle table below |
| `source` | string | `"Sentinel-2"`, `"GFW"`, `"Sentinel-2 + GFW"` (co-detection with justified combined confidence), or `"Planet NICFI"` — whichever source's confidence is currently displayed (see dominance rule). No `"Ensemble"` value; WBF/cross-tier score-blending is not used |

---

## Detection Record Lifecycle

Each detection record persists in `detections.json` and transitions through the following states. **Evaluated in priority order: `active` → `unconfirmed` → `inactive`** (an `unconfirmed` condition may technically overlap with `active`; `active` always wins).

```
active:      NICFI detection within the past 3 months
unconfirmed: (NICFI detection 3–6 months ago) OR (Sentinel-2 or GFW detection within the past 6 months)
inactive:    NICFI detection 6+ months ago (or never) AND Sentinel-2 detection 6+ months ago (or never) AND GFW detection 6+ months ago (or never)
```

Only NICFI detections can produce/confirm `active` status — Sentinel-2 and GFW alone (individually or together) can only ever push a record into `unconfirmed`. This reflects their shared role as early-warning triggers, not confirming sources (see Models section above).

| Status | Condition | Map display | Duplicate check |
|---|---|---|---|
| `active` | NICFI-confirmed within the past 3 months | Green `#3fb950`, pulsing | Yes |
| `unconfirmed` | NICFI 3–6 months ago, or Sentinel-2/GFW-only within 6 months | Yellow `#d29922`, static | Yes |
| `inactive` | No source within 6 months | Hidden | **No** |

**Worked example:** July 1 NICFI mosaic shows no airstrip. July 8 a new clandestine airstrip appears; Sentinel-2 (and/or GFW) flags the vegetation change same week → record inserted as `unconfirmed` (yellow) immediately. August 1 NICFI monthly mosaic confirms the shape → record upgraded to `active` (green). If NICFI never confirms it within 6 months of the early-warning flag, the record lapses to `inactive` (treated as a likely false positive).

### Duplicate detection logic

When a new detection arrives, the pipeline checks whether an existing record (in `active` or `unconfirmed` status) lies within **500 m** of the new coordinates:

- **Match found:** Always update `confirmed_at`. Update `confidence`/`source` per the dominance-on-write rule (see Models section above) — a NICFI detection always overwrites; a Sentinel-2 or GFW detection (or a justified Sentinel-2×GFW combined score) overwrites only if the existing record's `source` is not `"Planet NICFI"`. `detected_at` is left unchanged.
- **Match found (`inactive`):** Treat as a new independent detection — the airstrip may have been re-opened or a new one built nearby.
- **No match:** Insert as a new record with `status: "active"` if from NICFI, or `status: "unconfirmed"` if from Sentinel-2 and/or GFW.

### Why `inactive` records are retained

Records are never deleted. Setting `status: "inactive"` rather than removing the record serves two purposes:

1. **Historical record:** Provides a long-term dataset of airstrip activity (useful for reporting and trend analysis).
2. **Prevents false re-detection:** Ensures that a new nearby detection is not incorrectly merged with a stale record from a different operational period.

### Confidence decay and natural abandonment

As a clandestine airstrip is abandoned, vegetation gradually reclaims the cleared area. This is reflected naturally in the model confidence score over successive pipeline runs:

```
Freshly cleared   → confidence 0.9+  → status: active
Grass growing in  → confidence 0.7–0.8
Partially covered → confidence 0.5–0.6 → status: unconfirmed
Fully regrown     → not detected      → status: inactive (after 6 months)
```

---

## Dashboard UI — Status Indicator

Each detection popup card displays a small circular status indicator in the top-right corner, visually separating **freshness** (status) from **confidence** (marker colour).

| Indicator | Colour | Animation | Meaning |
|---|---|---|---|
| ● | Green `#3fb950` | Pulsing glow | `active` — confirmed within 3 months |
| ● | Yellow `#d29922` | Static | `unconfirmed` — not re-confirmed for 3–6 months |
| — | — | — | `inactive` — hidden from map |

The same indicators appear in the sidebar legend alongside the existing confidence colour legend.

**Design rationale:** Marker colour already encodes confidence level (red / orange / blue). Using a separate small dot for status avoids overloading a single visual channel and keeps both dimensions readable at a glance.

---

## Web Dashboard (Cloudflare Pages)

- **Framework:** Vanilla JS + Leaflet (`web/index.html`)
- **Hosting:** Cloudflare Pages (auto-deploy on push to `main`, publish directory: `web/`)
- **Data loading:** `web/data/detections.json` fetched at page load
- **Languages:** Japanese / English toggle
- **Features:** Confidence filter, source filter, interactive Leaflet map, detection popup cards with status indicator

### Deploy flow

```
git push (Workstation) → GitHub main → Cloudflare Pages auto-build → Live dashboard updated
```

No manual deploy step is required.

---

## Pending Items (as of 2026-07-01)

See [HANDOFF.md](HANDOFF.md) for the prioritized next-thread action list. Summary:

| Item | Owner | Status |
|---|---|---|
| Predecessor's Faster R-CNN model + 178-image dataset (Brazil, Planet NICFI) | Received | Analyzed — see [CONCEPT_NOTE.md](CONCEPT_NOTE.md) |
| Predecessor's trained model weights (.pth) | Self | Unconfirmed — may not have been received, needs follow-up |
| Run existing model on new imagery, generate ~500 candidate detections for staff review (step 3a) | Self | Not started |
| Build NDVI change-detection + shape-filter logic, generate ~500 candidate tiles for staff review (step 2a) | Self | Not started |
| GFW API client + step 2b/2c candidate extraction | Self | Not started |
| Candidate review site (`review/`, Cloudflare Pages + D1 + R2) | Self | **Built and deployed** — see `review/README.md`; currently loaded with dummy images only |
| Upload real candidate batches to review site (`py/pipeline/upload_candidates.py`), 2534 total across steps 2/3 | Self | Not started |
| Staff verification of 2534 candidates (true/false labeling) | Staff | Not started |
| Retrain as YOLO with combined dataset (178 + 2012 verified, steps 3a/3b/3c) | Self | Not started |
| WBF fate | Self | Decided — not used; see Models section above |
| Detections storage: `detections.json` direct-write → DB migration | Self | Agreed in principle; target DB (e.g. Cloudflare D1) and timing (before vs after pipeline implementation) not yet decided |
| Planet NICFI GEE API access (free tier) | Self | To set up |
| Copernicus Data Space API credentials | Self | To set up |
| GFW API credentials | Self | To set up |
| Slope / river / village distance data source | Self | To confirm with staff |
| Workstation SSH Deploy Key setup | Self | To set up after pipeline code complete |

---

## Technology Stack

| Layer | Technology |
|---|---|
| Object detection | YOLOv? (Ultralytics) |
| Satellite data | `sentinelhub` (Copernicus Data Space, Sentinel-1 + Sentinel-2), Planet SDK v2 (NICFI), GFW API (Integrated Deforestation Alerts) |
| Calibration | `scikit-learn` (isotonic regression for Sentinel-2/GFW curves, logistic regression for Sentinel-2×GFW and Sentinel-1 feature boosts) |
| Backend pipeline | Python 3.12 |
| Dashboard | Vanilla JS + Leaflet |
| Hosting | Cloudflare Pages |
| Candidate review site | Cloudflare Pages + Functions + D1 (verdicts) + R2 (images) — see `review/` |
| Source control | GitHub |
| Scheduler | Windows Task Scheduler |
| Package management | `uv` |
