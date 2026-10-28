# Analysis standard operating procedure (SOP)

All parameters live under `params` in `config/config.yaml`; this file explains what they mean and the statistical rules around them. Guiding principle: **specify first, look second; report effect sizes with 95% CIs, not just p-values.**

## Contents
1. General statistical rules
2. Bulk preprocessing
3. Track A: clinical and survival
4. Track B: molecular regulation
5. Track C: microenvironment (bulk deconvolution, single-cell, spatial)
6. Track D: immunotherapy and drugs
7. Convergence: balance score and ML model

## 1. General statistical rules
- Multiple testing: BH-FDR, report q-values. Only pre-specified primary hypotheses may stand on a raw p-value.
- Correlation: Spearman by default; report rho with a bootstrap 95% CI (1,000 resamples).
- Seed every random procedure with `project.seed`.
- Report primary and exploratory analyses separately; label post-hoc analyses.
- Register all statistics through stats fragments (see SKILL.md).

## 2. Bulk preprocessing
- GEO microarrays: use the normalised values in the series matrix; apply log2(x+1) if not yet on a log scale. When several probes map to one gene, keep the probe with the highest mean expression.
- TARGET-OS: log2(TPM+1) (or FPKM); drop near-silent genes (zero in > 90% of samples).
- Across cohorts: **z-score within each cohort, analyse each cohort separately, then meta-analyse.** Never ComBat-merge cohorts and run survival analysis on the merged matrix. ComBat is for visualisation or exploratory pooled analyses only, with cohort as a model covariate.
- Filter sample types strictly: primary tumours only; metastases and relapses are separate groups.

## 3. Track A: clinical and survival
- **Primary analysis**: Cox regression on continuous CXCL11 (within-cohort z-score), reported as HR per 1 SD.
- **Secondary analysis**: median split, Kaplan–Meier curves and log-rank test. A maxstat optimal cut-off is a sensitivity analysis only and must be labelled "data-driven".
- Check proportional hazards with `cox.zph`; if violated, report time-split or time-varying effects.
- Multivariable models: age, metastasis at diagnosis, chemotherapy response (where available). Keep at least 10 events per variable; drop covariates if events are too few.
- Meta-analysis: random effects (REML), pooled HR with 95% CI and I², forest plot.
- Nomogram with `rms`, bootstrap calibration (B = 1,000) and decision-curve analysis.

## 4. Track B: molecular regulation
- Co-expression among CXCL11, CXCR3, ACKR3, CXCL9/10/12 and IFN-γ pathway genes.
- Transcription-factor activity: decoupler with CollecTRI, focusing on STAT1 and IRF1.
- GSEA on Hallmark, Reactome and GO-BP, ranked by Spearman correlation with CXCL11 (rank-based, not group-based).
- CXCR3 vs ACKR3 balance: their correlation, their respective pathways, and their relation to CD8 infiltration.

## 5. Track C: microenvironment
**Bulk deconvolution**: at least three methods (MCP-counter, xCell, ESTIMATE, plus CIBERSORT or quanTIseq); report whether conclusions agree across methods. Confirm the LM22 licence before using CIBERSORT.

**Single-cell**
- QC: genes ≥ `min_genes`, mitochondrial fraction ≤ `max_mt_pct`; remove doublets with scrublet or scDblFinder.
- Workflow: log1p(CP10k) normalisation → 3,000 highly variable genes → PCA → Harmony integration by sample → Leiden clustering (resolution 0.6).
- Canonical markers for annotation:
  - osteoblastic tumour cells: RUNX2, SP7, ALPL, COL1A1
  - chondroblastic: SOX9, ACAN, COL2A1
  - osteoclasts: ACP5, CTSK, MMP9
  - myeloid: CD14, CD68, C1QA, LYZ
  - T cells: CD3D, CD3E, CD8A
  - NK cells: NKG7, GNLY, KLRD1
  - endothelium: PECAM1, VWF, CDH5
  - CAF/fibroblasts: DCN, LUM, ACTA2
  - pericytes: RGS5
  - B/plasma cells: MS4A1, CD79A, MZB1
- Malignant cells: copyKAT (or inferCNV) with immune cells as reference, cross-checked against tumour markers.
- **CXCL11 is very sparse in single-cell data.** Report detection fractions per cell type and combine pseudo-bulk and module scores; never conclude from a handful of positive cells.
- Cell–cell signalling: LIANA multi-method consensus. First confirm that CXCL11–CXCR3 and CXCL11–ACKR3 exist in the resource used; if missing, add them from the literature and flag them as custom pairs.
- Single-cell modules (e.g. the ACKR3⁺ endothelial module) are **defined in single-cell data only** and then transferred to bulk, to avoid leakage.

**Spatial transcriptomics** (only once a dataset is confirmed available): co-localisation or neighbourhood analysis of CXCL11 relative to CXCR3⁺ cells and ACKR3⁺ vessels.

## 6. Track D: immunotherapy and drugs
- Within osteosarcoma cohorts: TIDE and IPS predictions; correlation with checkpoint genes.
- ICB transfer validation: compute the axis score in each ICB cohort and test it against response (AUC and OR with 95% CI) and survival; meta-analyse across cohorts. **Always label as indirect evidence.**
- Drug sensitivity: oncoPredict trained on GDSC2; compare high vs low axis-score groups with BH correction.
- DepMap: CXCL11, CXCR3 and ACKR3 expression in osteosarcoma cell lines as supporting evidence.
- CMap/CLUE is optional and requires registration.

## 7. Convergence: balance score and ML model
**Axis balance score (ABS), pre-specified**
Osteosarcoma tumour cells express CXCR3 themselves (CXCR3A, pro-metastatic; PMID 40502679, 19544560), so bulk CXCR3 mixes T/NK and tumour sources and cannot serve as a recruitment marker on its own. See `docs/private/novelty_report.md`.
- **Primary definition (compartment modules)**, defined in single-cell data only:
  - each module = compartment markers plus genes co-expressed with CXCR3 or ACKR3 in that compartment, 10–30 genes;
  - **R_imm**: CXCR3⁺ effector module in T/NK cells;
  - **R_tum**: CXCR3⁺ module in tumour cells;
  - **S_endo**: ACKR3⁺ module in endothelium;
  - score the three modules in bulk with ssGSEA: **ABS = R_imm − (R_tum + S_endo)/2**.
- **Sensitivity definition**: z(CXCR3) − z(ACKR3).
- **Primary analyses**: ABS × CXCL11 interaction on survival; ABS vs immunotherapy response (ICB transfer validation).
- **Freeze the modules first**: write the gene lists into `config/` before touching any survival or response outcome.

**ML prognostic model (TRIPOD+AI)**
- Train on TARGET-OS only; validate externally on each GEO cohort.
- Nested CV (5 outer × 5 inner folds, 10 repeats). **Feature selection belongs inside the inner loop** to prevent leakage.
- Algorithms limited to CoxNet, RSF, GBM-Cox and CoxBoost. No "101 combinations" sweeps — they amount to selecting on the validation data.
- Metrics: Harrell's and Uno's C, time-dependent AUC at 3 and 5 years, calibration, decision curves.
- Sample size: ~88 patients with limited events, so keep features few (typically ≤ 10).
- Interpretability: SHAP (survex or shap), global importance and individual explanations.
- Head-to-head comparison with ≥ 10 published osteosarcoma signatures, each with a real PMID and genes checked against the original paper.

## Assay resolution

Treat CXCR3 isoform claims as unverified unless the assay and analysis resolve isoforms. Cell-type resolution does not by itself provide isoform resolution. Keep gene-level compartment associations separate from isoform-specific mechanistic claims.
