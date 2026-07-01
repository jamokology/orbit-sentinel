# GeoVigil Analytics — Concept Note

> Why this design, what the challenges were, and what alternatives were rejected.
> For detailed specifications, see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Background: Evaluation of the Predecessor's Model

The predecessor left a Faster R-CNN (ResNet-50 FPN) model trained on 178 images of illegal airstrips in the Brazilian Amazon (Planet NICFI imagery). Analysis revealed the following issues:

| Issue | Description |
|---|---|
| Insufficient data volume | 178 images is extremely small for object detection |
| No independent validation set | train/val was a random split from the same pool; performance on unseen data was never verified |
| Geographic bias | Brazil only; generalization to other regions such as Peru is unknown |
| No confidence threshold | All detections were output at inference time, with no false-positive filtering |
| NIR band unused | The 4-band imagery was converted to RGB, discarding the near-infrared band that is effective for vegetation detection |
| Inconsistent training configuration | Epoch/learning rate differ between the code and the report, giving low reproducibility |
| No mAP figures | Quantitative evaluation was effectively never performed |

→ Conclusion: **The model is usable as a starting point, but not usable in production as-is.** The greatest asset is the predecessor's know-how in ground-truth construction (integrating and filtering multiple data sources).

---

## Dataset Expansion Policy

### Options Considered and Reasons for Rejection

| Option | Reason for rejection |
|---|---|
| Search for a new dataset from scratch | Reliable third-party data sources are scarce; not realistic |
| Verify the entire pool via random sampling | Positive rate is below 0.01%, not worth the staff effort |
| Operate on change detection alone | Incompatible with the periodic re-confirmation logic for existing (long-abandoned) airstrips; the 3-month/6-month status transitions would not function |

### Adopted Policy: Active Learning (Staged, Human-in-the-Loop Data Expansion)

```
Detection with the existing Faster R-CNN model (no threshold) → staff review, 500 images
+
NDVI change detection (elongated-shape filter) candidate extraction → staff review, 500 images
+
Original 178 images (positives only)
─────────────────────────────
Total ~1178 images retrained with YOLO
```

**Why mix two sources:**
- Existing model detections → refines patterns the model already handles well, and leverages false positives (negatives) as training data
- Change detection → surfaces novel/atypical patterns the model tends to miss (addresses false negatives)

**Value of negative samples:** For both Faster R-CNN and YOLO, adding explicit negatives (confusable non-airstrip features such as farm roads, riverbanks, field boundaries) to the training data reduces false positives. The predecessor's 178 images were all positives, and the lack of confusable negative patterns is presumed to be one cause of false positives.

**Retraining cycle:** Repeat a similar process once every few years (3–10 year span), to keep pace with changes in airstrip construction methods and improvements in satellite image resolution.

---

## Role Division Between the Two Imagery Sources (Sentinel-2 and Planet NICFI)

The original plan (as documented in ARCHITECTURE.md) assumed training an independent YOLO model for each source. After review, this is changed as follows.

### Reason for the Change

Sentinel-2 has 10 m resolution, so an airstrip's width (15–30 m) spans only 1–3 pixels, making **independent shape-based judgment difficult**. Planet NICFI, at 4.77 m and already the standard for the predecessor's data, is therefore the sole source for shape-based confirmed detection.

### Finalized Role Division

| Source | Role | Frequency | Confirming power |
|---|---|---|---|
| **Planet NICFI** | Confirmed detection (YOLO inference, shape judgment) | Monthly, all of Peru | The only source that can promote a site to `active` |
| **Sentinel-2** | Early warning (change detection only, no shape judgment) | Weekly, clear-sky areas only | Registers `unconfirmed` only; never confirms |

### Status Transition Logic (Finalized)

Evaluation order: active → unconfirmed → inactive.

```
active:      NICFI detection within the last 3 months
unconfirmed: (NICFI detection 3-6 months ago) OR (Sentinel detection within the last 6 months)
inactive:    NICFI detection over 6 months ago AND Sentinel detection also over 6 months ago
```

**Concrete example (no airstrip in the 7/1 NICFI image, new airstrip opens 7/8, Sentinel detects the change on 7/8):**
1. 7/8 Sentinel change detection → immediately registered as `unconfirmed` (yellow)
2. 8/1 monthly NICFI update confirms it → promoted to `active` (green)
3. If NICFI does not confirm it within 6 months, it automatically becomes `inactive` (excluded as a possible Sentinel-only false positive)

**Confidence for Sentinel-only detections:** Not a fixed value; a variable confidence per detection is used instead. A confidence score is computed per detection from continuous features such as NDVI change magnitude, via a calibration curve (see "Construction Flow" below for details).

---

## Sentinel-2 Change Detection Output Format and Candidate Filters (Finalized)

**Output format: point coordinates + score** (bounding boxes are not used). At Sentinel-2's 10 m resolution, the airstrip width (1–3 pixels) yields no usable shape information, so a bounding box would only be "the bounding rectangle of the connected pixel blob with NDVI change," which does not improve accuracy. Point coordinates are also sufficient for duplicate matching (500 m proximity check).

**Ensuring real-time responsiveness:** Multiple consecutive confirmations are not used as a gating condition. Each time a clear image becomes available, it is immediately registered as an `unconfirmed` candidate, and confidence is incremented with each re-detection (realized via the confidence update in the existing duplicate detection logic; see ARCHITECTURE.md). This preserves early warning on a cycle as short as 5 days, while single-shot noise (cloud shadows, water reflections, etc.) naturally fails to accumulate confidence since it is not re-detected, and is thereby weeded out.

**Candidate filter conditions (finalized):**
- NDVI change detection (clearing / vegetation loss)
- Elongated-shape filter (aspect ratio)
- **Linearity filter** (added) — airstrips are close to straight lines; roads meander, rivers curve, and deforestation fronts are irregular in shape, making this useful for discrimination
- **Minimum length threshold** (added) — excludes typical small-scale clearing and farmland plots

→ "Isolation (distance from existing roads/rivers)" and "water-proximity exclusion (to exclude mining)" were not adopted. Only conditions directly tied to the airstrip's physical constraints (straightness, minimum length) were added; conditions that risk increasing false negatives were set aside.

**Note:** Sentinel-2 still cannot perform "airstrip-specific" identification, and false candidates from clearing, mining, etc. may be included. Final confirmation is the responsibility of NICFI (YOLO shape judgment); the two-stage design assumes false candidates are never promoted to `active` and automatically converge to `inactive` within 6 months (see ARCHITECTURE.md Models section).

### Parameter Tuning Policy (Finalized)

Initial parameters (NDVI threshold, aspect ratio, linearity residual, minimum length) are **intentionally set loose (biased toward capturing broadly)**, and recall assurance is delegated to this initial design decision. Staff review results (correct/incorrect labels) are fit to the distribution of change magnitude for true positives, and the threshold is determined by **extrapolating to the level that covers 99.9% confidence on that distribution** (not simply "the minimum observed TP value," but set so that even small change magnitudes not yet present in the observed data have some probability of being captured as TPs).

Rationale: exhaustive ground truth data to quantitatively verify false negatives cannot realistically be built. Using the 178 known airstrips (cases the predecessor's model clearly detected) for recall verification was considered, but this set carries a selection bias toward "easily identifiable airstrips" and is not representative of the borderline cases Sentinel-2 is prone to miss (early-stage construction, small clearings, cloud effects, etc.). Therefore, even if no misses occurred among the 178 images, this would not prove the filter is sufficiently loose, and the approach was rejected.

**Note on sample size:** When the number of TPs is small (tens to about a hundred), directly reading the 99.9th percentile (lower 0.1% point) off the empirical distribution makes tail estimation unstable. If the count is insufficient, a parametric estimate assuming, e.g., a log-normal distribution should be considered.

---

## Global Forest Watch (GFW) Integration and Additional Features (Finalized, added 2026-07-01)

Following discussion with field staff, the following three points were finalized.

### Adding GFW as an early-warning source running in parallel with Sentinel-2

[Global Forest Watch](https://www.globalforestwatch.org/)'s Integrated Deforestation Alerts (combining GLAD-L, GLAD-S2, RADD, and DIST-ALERT) are added as a **second early-warning source** running alongside Sentinel-2 change detection.

**What GFW actually is (resolution and update frequency are not uniform):**

| Sub-system | Satellite | Resolution | Update frequency |
|---|---|---|---|
| GLAD-L | Landsat (optical) | 30 m | Weekly |
| GLAD-S2 | Sentinel-2 (optical) | 10 m | Weekly (cloud-affected) |
| RADD | Sentinel-1 (SAR radar) | 10 m | Near-real-time (cloud-independent; gap-free coverage every 6-12 days in the tropics) |

Since the actual resolution and freshness of a given alert depends on which sub-system triggered it, GFW detections should retain a tag for which sub-system produced them, for possible future inclusion as a feature in GFW's calibration curve.

- **Role:** GFW also cannot confirm airstrip shape, so it is given the same role as Sentinel-2 — early warning only, never able to promote a record to `active`. The existing dominance rule (only NICFI can promote to `active`) is unchanged.
- **Confidence:** Sentinel-2's calibration curve (using NDVI change-magnitude margin as its feature) cannot be applied directly to GFW, since the feature definitions differ. A **separate calibration curve is built for GFW**, using GFW's own features (e.g., its ordinal confidence level: low/nominal/high).
- **Confidence fusion when both Sentinel-2 and GFW detect the same location:** A "corroboration boost" between NICFI and Sentinel-2 was previously rejected as "arbitrary without a proper probabilistic model" (see ARCHITECTURE.md). Sentinel-2 and GFW, however, are both non-confirming sources of the same kind — if correct/incorrect labels are available for candidates detected by both, `P(TP | Sentinel-2 margin, GFW feature)` can be estimated statistically (e.g., via logistic regression). This is adopted only where a genuinely data-driven fusion is possible, not an arbitrary boost constant (see "Construction Flow" below).
- **Future extensibility:** Since GFW data will also be useful for future features such as coca crop prediction, the GFW API client is implemented as a reusable, general-purpose module.

**Why build on GFW/RADD's ready-made alerts rather than our own Sentinel-1 (SAR) analysis:**

Sentinel-1 imagery is itself free (same CC BY 4.0 basis as RADD), but for now we rely on GFW/RADD's ready-made alerts rather than building our own SAR pipeline, for three reasons:

1. RADD's effective update cadence (6-12 days in the tropics) is not dramatically faster than Sentinel-2's clear-sky cadence (5 days); its real advantage is being cloud-independent, not raw speed
2. SAR-specific processing (speckle-noise removal, terrain-induced distortion correction) requires more specialized expertise than optical NDVI change detection, raising implementation and validation cost
3. RADD/GLAD are already finished alert products (point + ordinal confidence), so the calibration methodology used for Sentinel-2 (a continuous engineered feature + airstrip shape filters [aspect ratio, linearity, minimum length] + threshold extrapolation from the TP distribution) cannot be applied to them directly

**Future consideration (a custom Sentinel-1 layer):** If a dedicated Sentinel-1 layer with our own airstrip shape filters were built in the future, it could combine both "cloud independence" and "shape-tuned for airstrips" — something neither Sentinel-2 (shape-tuned but cloud-sensitive) nor GFW (cloud-independent but generic) achieves alone, potentially yielding a more accurate early-warning layer than either. However, SAR shape recognition is harder than optical due to speckle noise, so the need for a final NICFI shape confirmation stage would likely remain even then. This is not undertaken now; it is recorded as a candidate for a future retraining cycle.

### Slope and distance-to-river/village data (retained as additional features)

Field staff's empirical observations:
- Illegal airstrips tend to be located near rivers, roads, and existing villages
- Landslides only occur on sloped terrain, while illegal airstrips only exist on flat terrain, so slope data is useful for distinguishing the two (which are otherwise easily confused)

These are **not adopted as pre-detection exclusion filters** (for the same false-negative-risk reason that "isolation" and "water-proximity exclusion" were previously rejected — see above). Instead, slope, distance-to-river, and distance-to-village are retained as per-candidate metadata, and once enough True/False labels have accumulated from staff review, incorporating them into the confidence calculation will be considered **only if a statistically significant correlation is confirmed**. If no correlation is found, they will not be incorporated (retaining the data itself is low-cost, so this decision can be deferred).

---

### Construction Flow (Revised 2026-07-01)

Reorganized into two steps by purpose: Step 2 calibrates the early-warning logic itself (Sentinel-2 and GFW), while Step 3 collects YOLO training data via NICFI confirmation. Only step 3b assumes step 2 is complete. Dates below are illustrative examples; actual acquisition dates will be fixed at data-collection time.

**Image acquisition**
- Sentinel-2: acquired as weekly pairs at the same 7-day interval used in production (e.g., 2025-06-01 / 2025-06-08)
- Planet NICFI: one monthly mosaic (e.g., 2025-06-15)
- GFW: alerts for the same period as Sentinel-2, retrieved via API

**Step 2: Calibrating the early-warning logic (no NICFI, 700 images total)**

| Sub-step | Description | Count | Purpose |
|---|---|---|---|
| 2a | Run NDVI change detection on the 2025-06-01/06-08 pair (NDVI change magnitude, elongated shape, linearity, minimum length, all set loose) → staff correct/incorrect judgment | 500 | Extrapolate the Sentinel-2 threshold (99.9% confidence from the TP change-magnitude distribution) |
| 2b | Locations GFW detected but Sentinel-2's candidate generation missed → staff correct/incorrect judgment | 100 | Verify how much false-negative recovery GFW provides beyond Sentinel-2 alone |
| 2c | Locations Sentinel-2 detected but GFW did not, deliberately sampled → staff correct/incorrect judgment | 100 | Statistically test the Sentinel-2 × GFW joint-detection confidence boost (compared against the GFW-overlapping subset of 2a) |

- **Known limitation (regarding 2a):** In cases where partial regreening progresses after clearing, if the interval is longer (skipped due to cloud), the resulting change magnitude can be smaller than for a weekly interval, and may not be captured by parameters optimized for the weekly cadence. This is not resolved at this stage and is recorded as a known limitation.
- **Sampling method for 2b/2c:** 2a's 500 images remain a simple random sample. If the natural overlap rate with GFW turns out to be very high (e.g., 480 of 500 overlap), then 2a alone would contain only a small number of "Sentinel-2-only, no GFW" cases (e.g., ~20), which is insufficient to statistically test the boost effect — hence 2c is deliberately sampled separately. 2a's threshold calibration itself is computed on the unmodified random sample; 2b and 2c are tabulated as separate analyses.

**Step 3: YOLO training data collection (uses NICFI, 1000 images total; 3a and 3b can run in parallel, 3b assumes step 2 is complete)**

| Sub-step | Description | Count |
|---|---|---|
| 3a | Apply the existing Faster R-CNN (no threshold) to NICFI (2025-06-15) → staff correct/incorrect judgment | 500 |
| 3b | Apply 2a's logic to the next weekly pair (2025-06-08/06-15) → staff correct/incorrect judgment using the NICFI image at the same locations | 500 |

- Original 178 + 3a's 500 + 3b's 500 = **1178 images total** for new YOLO training
- Samples derived from 3b are tagged as "Sentinel-triggered" (not for confidence computation, but for traceability in future data re-evaluation and retraining cycles)

**Step 4: Parameter recalculation and variable-confidence calibration**
- Pool 2a's 500 images and 3b's 500 images (1000 total, treated as equally reliable labels since both are NICFI-verified), and recalculate the Sentinel-2 threshold at 99.9% confidence. This may end up looser than 2a alone.
- Fit a monotonic calibration curve (e.g., isotonic regression) relating each Sentinel-2 candidate's "margin from the threshold" (primarily NDVI change magnitude) to its correct/incorrect label, enabling variable, per-detection confidence (a fixed average-precision value is not used)
- Using 2b's data, build a separate calibration curve based on GFW's own features
- Compare 2a's GFW-overlapping subset against 2c to test whether a Sentinel-2 × GFW joint-detection confidence boost is statistically justified (e.g., via logistic regression on `P(TP | Sentinel-2 margin, GFW feature)`). If it cannot be justified, the boost is not adopted.
- **Limit to a single iteration:** Further loosening the threshold and re-collecting candidates again is not repeated, as the cost-effectiveness deteriorates rapidly. The next review is deferred to the retraining cycle a few years out.

**Total images for review: Step 2 (700) + Step 3 (1000) = 1700**

## Open Items

- Whether to adopt **Weighted Boxes Fusion (WBF)** — since the output format was finalized as point + score, WBF is likely unnecessary, with proximity matching alone being sufficient (leaning toward "not needed"). ARCHITECTURE.md needs to be updated to reflect this.
- Concrete initial values for the change-detection logic's parameters (NDVI threshold, aspect-ratio threshold, linearity residual tolerance, minimum length threshold; initial values are to be set toward capturing broadly)
- Target coverage area (all of Peru, or a limited pilot region)
- Choice of distribution-fitting method (empirical vs. parametric distribution) for cases with a small number of TPs
- Details of GFW API authentication and the features it provides (e.g., confidence levels)
- Final decision on whether/how to implement the Sentinel-2 × GFW confidence-boost fusion model (e.g., logistic regression)
- How to obtain slope and distance-to-river/village data (source, format) and how to attach it to candidate records
- If a statistically significant correlation between slope/distance data and correct/incorrect labels is confirmed, how specifically to incorporate it into the confidence calculation
- **(Future consideration, out of scope for now) A custom Sentinel-1 (SAR) airstrip-detection layer** — see the "GFW Integration" section above. Building a dedicated layer that is both cloud-independent and shape-tuned for airstrips could improve accuracy in the future, but is excluded from the current scope given the specialized expertise and implementation cost of SAR speckle-noise processing
