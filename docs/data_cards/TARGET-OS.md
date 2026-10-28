# TARGET-OS

> Descriptive values in this card (age, sex, site, follow-up, field counts) were computed while verifying the cohort and checked by hand; they are documentation, not registered statistics. Values used in figures or text are the registered `target_*` entries in `results/stats.json`.

- **Source / download date**: 2026-10-05.
  - Expression: UCSC Xena GDC hub (`TARGET-OS.star_tpm.tsv.gz`, `TARGET-OS.star_counts.tsv.gz`, plus probemap `gencode.v36.annotation.gtf.gene.probemap`).
  - Clinical: GDC open-access Clinical Supplements (`TARGET_OS_ClinicalData_Discovery_20230709.xlsx`, `TARGET_OS_ClinicalData_Validation_20230329.xlsx`).
  - File sizes and sha256 are listed in `data/raw/target_os/manifest.json`.
- **Platform and annotation**: RNA-seq (STAR, GDC harmonised). Xena values are log2(TPM+1). Ensembl IDs are mapped to gene symbols via GENCODE v36. Where several IDs share a symbol, the one with the highest mean expression is kept, leaving 59,427 genes.
- **Samples**: 88 RNA-seq samples. All 88 are primary tumours (barcode type `01`), one per patient. 87 of the 88 have a matching clinical record.
- **Expression scale and processing**: log2(TPM+1), used as delivered. Downstream analyses z-score genes within the cohort.
- **Clinical fields** (raw name → standard name):
  - `Age at Diagnosis in Days`/365.25 → `age`. Median 14.5 years, range 3.6–32.4.
  - `Gender` → `sex`. 50 male, 37 female.
  - `Primary tumor site` → `site`. Leg/foot 79, arm/hand 6, pelvis 2.
  - `Disease at diagnosis` → `metastasis_dx`. 22 metastatic at diagnosis.
  - `Histologic response` → `histologic_response`. Available for 35 patients only, so it cannot be used as a routine covariate.
- **Endpoints**:
  - **OS**: `Overall Survival Time in Days`/30.4375 → months. `Vital Status` Dead = 1, Alive = 0. 85 patients have OS data with 29 deaths. After excluding time ≤ 0, 84 patients are analysable. Median follow-up (reverse KM) is 61.3 months.
  - **EFS**: `Event Free Survival Time in Days` → months. `First Event` of Relapse, Death, Progression or Second Malignant Neoplasm = 1; Censored = 0. 85 patients, 41 events.
- **Known issues and how they are handled**:
  - The Xena `TARGET-OS.survival.tsv` has only 60 patients, so it is not used. The GDC original clinical tables are authoritative.
  - **First Event is blank for 33 patients.** All 33 are alive, and their EFS time equals their OS time, i.e. they had event-free follow-up. They are coded as censored (`py/prep_target.py`).
  - 3 patients have neither OS nor EFS data, and 1 RNA-seq patient has no clinical record.
- **Role in this study**: discovery cohort, and the training set for the ML model.
- **Verified**: yes (2026-10-05). Code: `py/fetch_target.py` → `py/prep_target.py`. Stats fragment: `results/stats/data_target_os.json`.
