# GeoVigil Analytics — System Architecture

> Clandestine airstrip detection platform for Peru  
> UNODC / GeoVigil Analytics Project

---

## Overview

GeoVigil Analytics is a satellite-imagery-based detection system that identifies clandestine airstrips in Peru using YOLO object detection models. Detection results are published to a web dashboard via an automated daily pipeline.

```
Satellite Imagery (Sentinel-2 + Planet NICFI)
        │
        ▼
  Workstation (Windows, shared PC)
  ├─ Weekly cron via Task Scheduler
  ├─ NICFI: YOLO inference (shape-based, confirming)
  ├─ Sentinel-2: change-detection logic (non-ML, trigger only)
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

Two complementary sources are used in parallel to maximize coverage and update frequency.

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

### Rationale for using both sources

| Scenario | Source used | Frequency |
|---|---|---|
| Clear sky over target area | Sentinel-2 | Up to weekly |
| Heavy cloud cover | Planet NICFI mosaic | Monthly (guaranteed) |
| Both available | Both — ensemble inference | Weekly / monthly |

Using both sources ensures that every target area receives at least one detection update per month regardless of cloud conditions, while clear-sky areas can be updated more frequently via Sentinel-2.

---

## Machine Learning Pipeline

> **Revised 2026-06-30** — see [CONCEPT_NOTE.md](CONCEPT_NOTE.md) for the reasoning behind this revision. The original two-independent-model + WBF design (kept below for history) has been replaced by a single confirming model (NICFI) plus a change-detection early-warning layer (Sentinel-2).

### Models (current design)

| Component | Imagery | Role | Confirms `active`? |
|---|---|---|---|
| `model_planet.pt` (YOLO) | Planet NICFI tiles | Main detection — shape-based object detection | Yes — only source that can confirm/upgrade to `active` |
| Change-detection logic (non-ML or lightweight) | Sentinel-2 tiles | Early warning — flags vegetation-clearing changes, no shape classification | No — only produces `unconfirmed` entries |

**Why Sentinel-2 has no independent YOLO model:** at 10 m resolution, a runway (15–30 m wide) spans only 1–3 pixels — too coarse for reliable shape-based classification. Sentinel-2's value is update frequency (weekly, clear-sky permitting), not shape discrimination. It is used as a trigger, not a confirmer.

**Sentinel-only detection confidence:** a per-detection variable confidence, not a fixed value. Each Sentinel-2 change-detection candidate has a continuous "margin" feature (primarily NDVI change magnitude relative to the decision threshold). A monotonic calibration curve (isotonic regression, fit against the staff-verification batches — see [CONCEPT_NOTE.md](CONCEPT_NOTE.md) "構築フロー") maps this margin to an empirical probability of being a true positive, used as the confidence score for that detection.

### Combining NICFI and Sentinel-2 confidence — no WBF, no score-blending (confirmed)

**Decided: WBF is not used, and confidences are never numerically fused (no weighted average).** The original rationale for WBF (merging two independent models' bounding boxes via IoU) assumed two YOLO models running in parallel with comparable, box-level scores. Under the revised design, Sentinel-2 no longer produces bounding boxes at all (point + score output only), so IoU-based fusion cannot apply mechanically. But beyond that: even the underlying idea of averaging the two confidence numbers is rejected, because the two scores measure different things (NICFI = shape-classification confidence; Sentinel = "is this NDVI change airstrip-like" proxy score with a much lower ceiling, since Sentinel cannot resolve shape at 10 m) and the two sources are not peers in the state machine — only NICFI can confirm/upgrade to `active`.

**Dominance rule (confirmed):** `confidence` is not derived from the current `status` — it is the score attached to the **most recent update event**, subject to dominance on write:
- A NICFI detection **always** overwrites `confidence`/`source` with its own YOLO score, regardless of what was there before.
- A Sentinel-2 detection overwrites `confidence`/`source` with its own calibrated score **only if the record's current `source` is not `"Planet NICFI"`** (i.e., Sentinel-2 may update a Sentinel-2-only record, but may never overwrite a NICFI-confirmed value).
- If no new detection arrives, `confidence`/`source` simply retain their last value — including through a `status` transition from `active` to `unconfirmed` (e.g., a NICFI-confirmed record aging past 3 months without reconfirmation still shows NICFI's last score, not a blank or Sentinel-derived value).
- A "corroboration boost" (small confidence increase when both sources independently flag the same location) was considered and **rejected** — the boost magnitude would be arbitrary without a proper probabilistic model, and adds complexity for unclear benefit. Not implemented.

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
    fetch_sentinel.py    # Sentinel-2 imagery retrieval (Copernicus Data Space)
    fetch_planet.py      # Planet NICFI monthly mosaic retrieval
    run_inference.py     # YOLO inference (NICFI only)
    change_detection.py  # Sentinel-2 NDVI change-detection + shape filters (non-ML)
    merge.py             # Dominance-rule merge (NICFI confirmation wins; no WBF/score-blending)
    update_json.py       # Update detections.json (dedup + status management)
    git_push.py          # Commit and push to GitHub
  daily_run.py           # Entry point called by Task Scheduler
web/
  data/
    detections.json      # Output consumed by the web dashboard
```

### Execution schedule

- **Trigger:** Windows Task Scheduler, weekly (e.g., every Monday 02:00 local time)
- **Steps:**
  1. Fetch latest Sentinel-2 imagery for target regions (skip if cloud cover > 20%)
  2. Fetch latest Planet NICFI mosaic if a new monthly mosaic is available
  3. Run NICFI YOLO inference and/or Sentinel-2 change detection on available imagery
  4. Merge results using the dominance rule (see Models section) — no WBF, no score-blending
  5. Write `data/detections.json`
  6. `git commit` + `git push` to `main` branch

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
| `confidence` | float (0–1) | Confidence of the confirming source only — see "Combining NICFI and Sentinel-2 confidence" above. Not a blended/ensembled value; `"active"` records show NICFI's YOLO score, `"unconfirmed"` records show Sentinel-2's calibrated score |
| `detected_at` | string | Timestamp of first detection |
| `confirmed_at` | string | Timestamp of most recent detection (updated each pipeline run) |
| `status` | string | See lifecycle table below |
| `source` | string | `"Sentinel-2"` or `"Planet NICFI"` — whichever source's confidence is currently displayed (see dominance rule). No `"Ensemble"` value; WBF/score-blending is not used |

---

## Detection Record Lifecycle

Each detection record persists in `detections.json` and transitions through the following states. **Evaluated in priority order: `active` → `unconfirmed` → `inactive`** (an `unconfirmed` condition may technically overlap with `active`; `active` always wins).

```
active:      NICFI detection within the past 3 months
unconfirmed: (NICFI detection 3–6 months ago) OR (Sentinel-2 detection within the past 6 months)
inactive:    NICFI detection 6+ months ago (or never) AND Sentinel-2 detection 6+ months ago (or never)
```

Only NICFI detections can produce/confirm `active` status — Sentinel-2 alone can only ever push a record into `unconfirmed`. This reflects Sentinel-2's role as an early-warning trigger, not a confirming source (see Models section above).

| Status | Condition | Map display | Duplicate check |
|---|---|---|---|
| `active` | NICFI-confirmed within the past 3 months | Green `#3fb950`, pulsing | Yes |
| `unconfirmed` | NICFI 3–6 months ago, or Sentinel-2-only within 6 months | Yellow `#d29922`, static | Yes |
| `inactive` | Neither source within 6 months | Hidden | **No** |

**Worked example:** July 1 NICFI mosaic shows no airstrip. July 8 a new clandestine airstrip appears; Sentinel-2 flags the vegetation change same week → record inserted as `unconfirmed` (yellow) immediately. August 1 NICFI monthly mosaic confirms the shape → record upgraded to `active` (green). If NICFI never confirms it within 6 months of the Sentinel-2 flag, the record lapses to `inactive` (treated as a likely Sentinel-2 false positive).

### Duplicate detection logic

When a new detection arrives, the pipeline checks whether an existing record (in `active` or `unconfirmed` status) lies within **500 m** of the new coordinates:

- **Match found:** Always update `confirmed_at`. Update `confidence`/`source` per the dominance-on-write rule (see Models section above) — a NICFI detection always overwrites; a Sentinel-2 detection overwrites only if the existing record's `source` is not `"Planet NICFI"`. `detected_at` is left unchanged.
- **Match found (`inactive`):** Treat as a new independent detection — the airstrip may have been re-opened or a new one built nearby.
- **No match:** Insert as a new record with `status: "active"` if from NICFI, or `status: "unconfirmed"` if from Sentinel-2.

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

## Pending Items (as of 2026-06-30)

See [HANDOFF.md](HANDOFF.md) for the prioritized next-thread action list. Summary:

| Item | Owner | Status |
|---|---|---|
| Predecessor's Faster R-CNN model + 178-image dataset (Brazil, Planet NICFI) | Received | Analyzed — see [CONCEPT_NOTE.md](CONCEPT_NOTE.md) |
| Run existing model on new imagery, generate ~500 candidate detections for staff review | Self | Not started |
| Build NDVI change-detection + shape-filter logic, generate ~500 candidate tiles for staff review | Self | Not started |
| Staff verification of ~1000 candidates (true/false labeling) | Staff | Not started |
| Retrain as YOLO with combined dataset (178 + ~1000 verified) | Self | Not started |
| Decide WBF fate now that Sentinel-2 has no independent model | Self | Open question |
| Planet NICFI GEE API access (free tier) | Self | To set up |
| Copernicus Data Space API credentials | Self | To set up |
| Workstation SSH Deploy Key setup | Self | To set up after pipeline code complete |

---

## Technology Stack

| Layer | Technology |
|---|---|
| Object detection | YOLOv? (Ultralytics) |
| Ensemble | `ensemble-boxes` (WBF) |
| Satellite data | `sentinelhub` (Copernicus Data Space), Planet SDK v2 |
| Backend pipeline | Python 3.12 |
| Dashboard | Vanilla JS + Leaflet |
| Hosting | Cloudflare Pages |
| Source control | GitHub |
| Scheduler | Windows Task Scheduler |
| Package management | `uv` |
