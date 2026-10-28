# Dataset catalogue and verification protocol

`config/config.yaml` is the single source of truth; this file explains how to obtain and verify the data. Sample sizes below are **expected values** — always use the numbers parsed from the downloaded files.

## Catalogue

| ID | Type | Expected n | Endpoints | Role | How to obtain |
|---|---|---|---|---|---|
| TARGET-OS | RNA-seq | ~88 | OS, EFS | discovery | UCSC Xena GDC hub + GDC clinical supplements (`py/fetch_target.py`) |
| GSE21257 | Illumina array | 53 | OS, metastasis-free survival | validation | GEO series matrix (`py/fetch_geo.py`) |
| GSE16091 | HG-U133A | 34 | OS | validation | as above |
| GSE39055 | WG-DASL | 37 | OS, recurrence | validation | as above |
| GSE42352 | Illumina array | ~84 tumours | metastasis-free survival | validation, normal reference | as above; contains cell lines and MSCs — filter by sample type |
| GSE152048 | 10x scRNA | 11 | — | single-cell atlas | GEO supplementary files (large; separate rule) |
| GSE162454 | 10x scRNA | 6 | — | single-cell atlas | as above |
| JHO 2024 OS spatial | spatial transcriptomics | ? | — | spatial co-localisation | confirm availability and repository first |
| IMvigor210 | RNA-seq | ~348 | response, OS | ICB transfer validation | IMvigor210CoreBiologies package |
| GSE91061 | RNA-seq | ~109 | response | ICB transfer validation | GEO |
| GSE78220 | RNA-seq | ~28 | response | ICB transfer validation | GEO |
| PRJEB23709 | RNA-seq | ~91 | response | ICB transfer validation | ENA (raw reads; prefer published processed matrices) |
| DepMap | cell lines | — | dependency | supporting evidence | DepMap portal release files |
| GDSC2 | drug response | — | IC50 | oncoPredict training set | bundled with oncoPredict or the GDSC website |
| TCGA-SARC | RNA-seq | ~260 | OS | pan-sarcoma sensitivity analysis | Xena |

None of the ICB cohorts are osteosarcoma — **indirect evidence only**.

## Verification protocol (every cohort)

1. Parse the downloaded files with a script; never copy numbers from a web page by hand.
2. Record: actual sample count; count after filtering by sample type (tumour, cell line, normal); platform; expression scale (a maximum > 50 usually means not yet logged); survival time units and event coding; missingness.
3. Write a data card `docs/data_cards/<ID>.md` using the template below.
4. Set `verified: true` for the cohort in `config.yaml` and correct `n_expected`.
5. If the count differs from the literature, explain why in the card (duplicates, missing follow-up, …).

## Data card template

```markdown
# <ID>
- Source / download date / files and sha256:
- Platform and annotation (GPL, probe-to-gene rule):
- Samples: raw n → filtered n (filter rule)
- Expression scale and processing:
- Clinical variables (field → standard name):
- Endpoints: time unit, event coding, median follow-up, number of events
- Known issues and handling:
- Role in this study:
```

## Standard clinical field names

`sample_id, patient_id, age, sex, site, metastasis_dx, histologic_response, os_time_months, os_event, efs_time_months, efs_event, mfs_time_months, mfs_event, cohort`. Times in months; events coded 1/0.
