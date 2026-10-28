# Marrow visual system and figure standards

Art and utility meet in one principle: **an entity always has the same colour in every figure.** Crimson always means CXCL11, teal always CXCR3/T cells, violet always ACKR3/endothelium.

## Palette (single source: `style/palette.json`)

| Entity | Colour | Use |
|---|---|---|
| CXCL11 | `#c8243c` crimson | lead gene, high-expression group, chemokine gradient in schematics |
| CXCR3 / T cells | `#00897b` teal | CXCR3, CD8⁺ T cells |
| ACKR3 / endothelium | `#6a4fb8` violet | ACKR3, vascular endothelium |
| Myeloid | `#c47f00` amber | macrophages, monocytes |
| Osteoclasts | `#d0559a` magenta | |
| NK | `#4a9a2e` green | |
| Fibroblasts / CAF | `#2f6db5` blue | also the low-expression group |
| Osteoblastic tumour cells | `#a8662e` sienna | |
| Other | `#b9b3a8` bone grey | any 9th+ cell type folds into "other" |

- **High vs low groups**: crimson `#c8243c` vs blue `#2f6db5` (CVD ΔE 19.3, normal-vision ΔE 29.3).
- **Continuous expression** (feature plots, heat-map intensity): `os_seq`, bone white → crimson.
- **Correlation and z-scores**: `os_div`, blue–bone white–crimson, zero fixed at the midpoint.
- The palette passed colour-vision-deficiency and contrast checks (recorded under `validation` in `palette.json`). **Never add ad-hoc colours.**

## Rules
- **Font**: Arial; minimum 7 pt, panel titles 8 pt bold, panel letters 9 pt bold (a, b, c …).
- **Size**: single column 85 mm, 1.5 columns 120 mm, double column 180 mm; height ≤ 225 mm.
- **Output**: vector PDF (editable text) plus 600 dpi LZW TIFF via `os_save()` (R) or `save_figure()` (Python).
- **Lines**: axes 0.3–0.4 pt, data lines 1 pt; only faint horizontal grid lines.
- **Scatter/UMAP**: with more than three categories, label clusters directly at their centres (colours cannot all be pairwise distinct); points 0.5–2 pt, semi-transparent allowed.
- **KM curves**: include a number-at-risk table; HR and p-values use the stats `display` values, never hand-typed.
- **Forest plots**: one row per cohort, pooled estimate last (diamond); I² in the legend.
- **Never**: dual y-axes, rainbow scales, 3D pies, decorative shadows or gradients, generative-AI imagery.

## The eight main figures

1. **Study design and graphical abstract**: four-track convergence flow plus the bone cross-section mechanism schematic (hand-built vector).
2. **Multi-cohort prognosis**: KM curves per cohort, per-SD HR forest plot, meta-analysis.
3. **Bulk immune microenvironment**: multi-method infiltration heat map (`os_div`), CD8/IFN-γ correlations, hot/cold classification.
4. **Single-cell atlas**: UMAP (direct labels), CXCL11 source dot plot (with detection fractions), cell–cell signalling chord or dot plot.
5. **CXCR3 vs ACKR3 balance**: receptor distribution across cells, ABS distribution, ABS × CXCL11 interaction, spatial co-localisation (if data exist).
6. **ML model**: nested-CV results, external C-index, SHAP beeswarm, nomogram and calibration.
7. **Immunotherapy and drugs**: TIDE/IPS, ICB transfer-validation forest plot (marked "indirect evidence"), drug sensitivity.
8. **Interactive atlas**: module screenshots and architecture.

## Graphical abstract and mechanism schematics
- Hand-built vector graphics (code or Inkscape): cortical and trabecular bone, tumour island, CXCL11 gradient (crimson fading out), recruited T cells (teal), scavenging vessel (violet).
- Background bone ivory `#faf7f0`; clean lines, generous white space, clear hierarchy. Label hypotheses as "Hypothesis".
- No licensed asset libraries (e.g. BioRender) unless the user has a licence that permits publication.

## Figure review checklist (shared by figure-artist and reviewer-2)
- [ ] every colour comes from palette.json and entity–colour mapping is consistent across figures
- [ ] no text below 7 pt; width matches single or double column
- [ ] every statistic comes from stats.json
- [ ] every panel has axis titles with units and a complete legend
- [ ] readable under colour-vision-deficiency simulation and in greyscale
- [ ] panel letters match the legend order
- [ ] no AI-generated imagery
