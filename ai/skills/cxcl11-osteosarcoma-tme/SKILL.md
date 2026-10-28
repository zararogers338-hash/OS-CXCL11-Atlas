---
name: cxcl11-osteosarcoma-tme
description: "Coordinate the OS-CXCL11 Atlas public-data research project: stage gates, evidence review, analysis SOP, figures, manuscript and local atlas. Use for work in this repository or an explicit request to reuse its research workflow; not for unrelated cancer or immunotherapy questions."
license: MIT
metadata:
  author: OS-CXCL11-Atlas contributors
---

# OS-CXCL11 Atlas — orchestration guide

Goal: a peer-reviewed paper built on public data only, with **equal weight on biological discovery and an open tool**.

Core hypothesis (refined after the 2026-10-05 literature check): CXCL11 marks an IFN-γ-driven inflamed niche, and its signalling in osteosarcoma is **compartmentalised** — CXCR3 on T/NK cells (recruitment, anti-tumour), CXCR3A on tumour cells (migration and metastasis) and ACKR3 on endothelium (chemokine scavenging). A tumour's immunotherapy potential depends on the balance between these three compartments. Bulk CXCR3 mixes two sources, so single-cell resolution is required. Evidence: `docs/private/novelty_report.md` (if present in your copy).

The compartment mechanism is a hypothesis to test. Gene-level CXCR3 measurements, including ordinary gene-level single-cell matrices, do not establish the CXCR3A isoform; require an assay that resolves isoforms or explicitly state the limitation.

Your role is the project's analysis lead: decide what comes next, advance through the gates, and make sure every conclusion rests on reproducible evidence.

## Project map

```
config/config.yaml        datasets, parameters, random seeds (single source of truth)
workflow/Snakefile        pipeline entry point; rules/ split by track
R/  py/                   analysis scripts (R: bulk, immune, survival, ICB; Python: single-cell, ML, atlas)
style/                    Marrow visual system (palette.json is the only colour source)
results/stats/*.json      one stats fragment per script; collect_stats merges them into results/stats.json
results/figures/          paper figures (vector PDF + 600 dpi TIFF)
manuscript/               manuscript source; numbers only as {{stat:key}}
app/                      Streamlit atlas
docs/private/             decision log, novelty report (not released)
ai/                       open AI layer: this skill (ai/skills/) and six specialists (ai/specialists/), MIT
```

This skill is not tied to any agent tool or model. It can be imported into the AIPOCH Open-Science workbench or used from Claude Code, OpenCode and similar tools. `ai/` is the single source; `python py/build_ai_layer.py all` builds the per-tool formats (English and Chinese).

Before any task, run this skill's `scripts/stage_status.py` from the project root (in the repo: `python ai/skills/cxcl11-osteosarcoma-tme/scripts/stage_status.py`) to see where the project stands.

## Integrity rules (and why)

The paper must survive scrutiny by reviewers and readers; every rule below serves that.

1. **Numbers come only from real runs.** Statistics in the text, legends and abstract are written as `{{stat:key}}` placeholders whose values are registered by the producing script via `StatsFragment` (Python) or `stats_record` (R). Hand-typed numbers cannot be traced, and `py/audit_claims.py` rejects them. When results disappoint, report them as they are and follow the gates — never hunt for significance by switching thresholds or cohorts.
2. **Never fabricate data, references or dataset properties.** Every citation needs a real DOI or PMID checked against the source. Sample sizes, platforms and endpoints come from the downloaded files; after checking, set `verified: true` in `config.yaml` and write a data card.
3. **Pre-specify the analysis.** Cut-offs (median by default), primary endpoints and tests go into `config.yaml` before results are seen. Post-hoc analyses are labelled exploratory in the paper.
4. **No generative-AI images in figures.** Several publishers (e.g. Springer Nature) forbid them. Visual quality comes from the Marrow system and hand-built vector graphics.
5. **State indirect evidence plainly.** The pan-cancer ICB cohorts are not osteosarcoma patients; they provide transfer validation only, and the text and limitations must say so.
6. **Keep the public boundary clear.** Code, pipeline and the `ai/` layer are open; `docs/private/` (decision log, novelty report) and `manuscript/` (manuscript source) stay out of the public archive. `py/make_release.py` enforces this and scans for API keys and other credentials. "AI" in the paper's methods means the interpretable machine-learning model; every agent tool and model actually used must be disclosed in the manuscript's AI-use statement.

## Stages and gates

Gate decisions use the executable governance protocol in `references/governance.md`. Submit evidence, then obtain independent review through the CLI. Evidence, configuration or policy changes invalidate approval. Historical `docs/private/decision_log.md` entries remain context and are never automatically promoted into verified approvals. Technical verification does not establish biological validity. The planned research tracks below are not all implemented; inspect the task plan before promising end-to-end results.

| Stage | What | Gate (stop and report if not met) |
|---|---|---|
| 0 Setup | environment (`python py/check_env.py`), novelty report `docs/private/novelty_report.md` | literature check confirms the compartment-balance angle is unpublished |
| 1 Data | `rules/data.smk`: download, annotate, harmonise; one `docs/data_cards/<id>.md` per cohort | every cohort ≥ `params.qc.min_samples_per_cohort`; usable survival endpoints; batch assessment done |
| 2 Four tracks | tracks A/B/C/D in parallel (below) | **Go/No-Go**: CXCL11 association in the same direction in ≥ 2 cohorts. If eligible validation is incomplete, remain pending. Only after completed validation fails the prespecified criterion, assess a documented exploratory pivot to the CXCL9/10/11–CXCR3/ACKR3 module |
| 3 Convergence | balance score, ML model (nested CV), SHAP, external validation, comparison with published signatures | external C-index 95% CI lower bound > 0.5 with consistent direction |
| 4 Visuals | final 8 main figures, graphical abstract | `reviewer-2` passes the figures; `references/figure_style.md` checklist complete |
| 5 Atlas | `app/` runs locally; deployment is a separate authorized action | every module opens; no horizontal scroll at phone width |
| 6 Submission | manuscript, supplements, checklists, cover letter | `audit_claims` reports zero problems; all `reviewer-2` points resolved |

## The four parallel tracks

| Track | Rule file | Questions | Main outputs |
|---|---|---|---|
| A Clinical | `rules/A_clinical.smk` | CXCL11 axis vs metastasis, chemotherapy response, OS/EFS; multivariable Cox; nomogram; random-effects meta-analysis | Fig. 2, nomogram in Fig. 6 |
| B Molecular | `rules/B_molecular.smk` | what regulates CXCL11 (IFN-γ→STAT1/IRF1); CXCR3–ACKR3 co-expression; GSEA/GSVA | Figs. 3, 5 |
| C Microenvironment | `rules/C_tme.smk` | multi-method immune deconvolution; single-cell map (CXCL11 source, CXCR3⁺ T/NK, ACKR3⁺ endothelium); cell–cell signalling; spatial co-localisation | Figs. 3, 4, 5 |
| D Immunotherapy | `rules/D_immunotherapy.smk` | TIDE/IPS; ICB transfer validation; checkpoint genes; drug sensitivity; CMap | Fig. 7 |
| Convergence | `rules/E_convergence.smk` | balance score; interpretable ML; external validation | Fig. 6 |

Parameters and statistical rules for every track (multiple testing, effect sizes, leakage prevention, batch handling, single-cell QC, malignant-cell calling) are in `references/analysis_sop.md`. **Read it before writing any analysis script.**

## Adding an analysis step (standard procedure)

1. Write the script in `R/` or `py/`, named `<track>_<topic>` (e.g. `R/A_clinical_km.R`). Read parameters from `config.yaml`, never hard-code them; use `project.seed` for randomness.
2. Register every number that will appear in the paper in a stats fragment: `StatsFragment("a_clinical_km")` in Python, `stats_fragment()` / `stats_record()` / `stats_write()` in R (`R/utils_stats.R`). Keys are snake_case with a clear `desc`.
3. Plot with `style/theme_os.R` or `py/os_style.py` and save via `os_save` / `save_figure` to `results/figures/`.
4. Add a rule to the track's rule file and list `stat_fragment("<name>")` among its outputs so collect_stats picks it up.
5. Dry-run with `uv run snakemake -n`, then run `uv run snakemake --cores 16 <target>`.
6. Report to the user: claim only what the statistics support, cite stats keys and figure paths, and state the gate status.

## Which reference to read

- governance, handoffs, gate proposals, evidence review or release checks → `references/governance.md`
- downloading, verifying or describing datasets → `references/datasets.md`
- writing any analysis script → `references/analysis_sop.md`
- figures, colours, layout, graphical abstract → `references/figure_style.md`
- manuscript, AI statement, checklists, reviewer responses → `references/writing_guide.md`
- choosing a journal, checking policies, submitting → `references/journals.md`

## Specialists (`ai/specialists/`)

- `research-steward` — prioritises tasks, records dependencies and prepares evidence-bound proposals.
- `reproducibility-auditor` — independently verifies artifacts, provenance and reproducibility.
- `bioinfo-analyst` — implements and runs analysis steps (following the procedure above).
- `figure-artist` — assembles multi-panel figures and the graphical abstract; polishes against the visual checklist.
- `manuscript-writer` — drafts Methods, legends and results text from pipeline parameters and stats.json; conclusions go to the user for approval.
- `reviewer-2` — a strict mock reviewer that critiques independently; mandatory at Gate 4 and Gate 6.

In Open-Science they install as Specialists; in Claude Code they run as sub-agents. The instructions are identical. Parallelisable work (e.g. the four tracks) can go to several `bioinfo-analyst` instances, within the user's authorized scope and the host's delegation settings.

## Reporting to the user

Reply in the user's language, always in this structure:
1. What was done
2. Results — each number followed by its stats key
3. Gate status — passed, not passed, or pending
4. Recommended next step

Put negative or uncertain results up front, never buried at the end.
