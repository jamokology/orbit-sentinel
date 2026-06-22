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
  ├─ YOLO inference (two models)
  ├─ Ensemble via WBF
  └─ git push → data/detections.json
        │
        ▼
  GitHub Repository (main branch)
        │
        ▼
  Cloudflare Pages (auto-deploy)
        │
        ▼
  Web Dashboard (Streamlit)
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

### Models

Two separate YOLO models are trained and maintained:

| Model | Training imagery | Status |
|---|---|---|
| `model_nicfi.pt` | Planet NICFI tiles | To be trained / inherited from predecessor |
| `model_sentinel.pt` | Sentinel-2 tiles | To be trained / inherited from predecessor |

Each model is trained on imagery from its respective source to preserve domain consistency. Cross-source inference (e.g., running a NICFI-trained model on Sentinel imagery) degrades accuracy and is avoided.

### Ensemble Inference — Weighted Boxes Fusion (WBF)

When detections from both models are available for the same geographic area, results are merged using **Weighted Boxes Fusion (WBF)**.

**Why WBF over simple NMS averaging:**
- NICFI (4.77 m) and Sentinel-2 (10 m) have different resolutions, so bounding box coordinates for the same airstrip will not align perfectly. WBF handles this by computing a weighted average of overlapping boxes rather than simply suppressing duplicates.
- WBF is the current standard for multi-model object detection ensembling and is recommended by Ultralytics (YOLO).

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

---

## Pipeline Execution (Workstation)

### Directory structure

```
py/
  pipeline/
    fetch_images.py      # Satellite image retrieval (Sentinel-2 + NICFI)
    run_inference.py     # YOLO inference per source
    ensemble.py          # WBF ensemble logic
    export_json.py       # Write detections.json
    git_push.py          # Commit and push to GitHub
  daily_run.py           # Entry point called by Task Scheduler
data/
  detections.json        # Output consumed by the web dashboard
```

### Execution schedule

- **Trigger:** Windows Task Scheduler, weekly (e.g., every Monday 02:00 local time)
- **Steps:**
  1. Fetch latest Sentinel-2 imagery for target regions (skip if cloud cover > 20%)
  2. Fetch latest Planet NICFI mosaic if a new monthly mosaic is available
  3. Run inference on available imagery
  4. Merge results with WBF if both sources produced detections
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
      "source": "ensemble"
    }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `generated_at` | ISO 8601 string | Pipeline execution timestamp |
| `is_demo` | boolean | `true` for demo/test data, `false` for real detections |
| `lat` / `lon` | float | WGS84 coordinates of detected airstrip centroid |
| `confidence` | float (0–1) | Model confidence score (post-ensemble), updated each time re-confirmed |
| `detected_at` | string | Timestamp of first detection |
| `confirmed_at` | string | Timestamp of most recent detection (updated each pipeline run) |
| `status` | string | See lifecycle table below |
| `source` | string | `"sentinel2"`, `"nicfi"`, or `"ensemble"` |

---

## Detection Record Lifecycle

Each detection record persists in `detections.json` and transitions through the following states:

| Status | Condition | Map display | Duplicate check |
|---|---|---|---|
| `active` | Confirmed within the past 3 months | Red marker, fully opaque | Yes |
| `unconfirmed` | Not re-confirmed for 3–6 months | Grey marker, semi-transparent | Yes |
| `inactive` | Not re-confirmed for 6+ months | Hidden | **No** |

### Duplicate detection logic

When a new detection arrives, the pipeline checks whether an existing record lies within **500 m** of the new coordinates:

- **Match found (`active` or `unconfirmed`):** Update `confirmed_at`, `confidence`, and `source`; keep `detected_at` unchanged.
- **Match found (`inactive`):** Treat as a new independent detection — the airstrip may have been re-opened or a new one built nearby.
- **No match:** Insert as a new record with `status: "active"`.

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

## Web Dashboard (Cloudflare Pages)

- **Framework:** Streamlit (`py/app.py`)
- **Hosting:** Cloudflare Pages (auto-deploy on push to `main`)
- **Data loading:** `data/detections.json` is read at app startup with a 1-hour cache (`@st.cache_data(ttl=3600)`)
- **Languages:** Spanish (default) / English toggle
- **Features:** Confidence filter slider, interactive Folium map, detection table

### Deploy flow

```
git push (Workstation) → GitHub main → Cloudflare Pages auto-build → Live dashboard updated
```

No manual deploy step is required.

---

## Pending Items (as of 2026-06-22)

| Item | Owner | Status |
|---|---|---|
| YOLO model file(s) from predecessor | Predecessor / colleague | Awaiting |
| Training dataset (labeled imagery) | Predecessor / colleague | Awaiting |
| Sample input images (to confirm format) | Predecessor / colleague | Awaiting |
| Confirm which imagery source was used for training | Predecessor | Awaiting |
| Planet NICFI GEE API access (free tier) | Self | To set up |
| Copernicus Data Space API credentials | Self | To set up |
| Workstation SSH Deploy Key setup | Self | To set up after pipeline code complete |

---

## Technology Stack

| Layer | Technology |
|---|---|
| Object detection | YOLOv? (Ultralytics) |
| Ensemble | `ensemble-boxes` (WBF) |
| Satellite data | `sentinelsat` / `eodag`, Google Earth Engine Python API |
| Backend pipeline | Python 3.12 |
| Dashboard | Streamlit + Folium |
| Hosting | Cloudflare Pages |
| Source control | GitHub |
| Scheduler | Windows Task Scheduler |
| Package management | `uv` |
