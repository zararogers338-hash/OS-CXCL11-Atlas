# Writing guide

## Numbers
- Every statistic in the text, abstract and legends is `{{stat:key}}`; use `{{stat:key|ci}}` to include the 95% CI.
- Sample sizes and event counts are registered in stats fragments too — never typed by hand.
- Run `python py/audit_claims.py manuscript/*.md` before rendering; it must report zero problems.
- Lines containing non-statistical numbers (gene names, platform IDs such as IL-2 or GPL96) may carry `<!-- audit:allow -->`.

## Structure (IMRaD)
**Title**: disease, axis, key finding and tool — e.g. "Compartmental CXCL11–CXCR3/ACKR3 signalling in osteosarcoma: multi-cohort analysis and an interactive atlas" (hypothetical). Fix the title only after the results are in; nothing unsupported goes into it.

**Abstract** (structured, ~250 words): Background → Methods (cohorts, sizes, methods) → Results (3–4 key numbers) → Conclusions (wording matched to the strength of evidence).

**Introduction** (4 paragraphs):
1. Osteosarcoma today and the failure of immunotherapy in it.
2. CXCR3 ligands in T-cell recruitment.
3. What is special about CXCL11: the only CXCR3 ligand that also binds ACKR3, which is expressed on osteosarcoma vasculature.
4. The gap and the aims of this study.

**Methods**:
- data sources (key points of each data card)
- preprocessing
- methods per track
- ML model (item by item against TRIPOD+AI)
- statistics
- code availability
- AI-use statement

**Results**: follow the order of the eight figures; each paragraph states the question, then the result, then one sentence on its meaning.

**Discussion**:
- main findings
- comparison with prior work — cite the 2019 osteosarcoma CXCR3 study and the CXCL10–CXCR3 dual-role work
- mechanistic interpretation (clearly labelled as speculative)
- clinical implications
- limitations (mandatory list below)
- conclusion

## Mandatory limitations
- Public data only, no wet-lab validation; findings are associations, not proof of causation.
- ICB cohorts are not osteosarcoma patients; transfer validation is indirect evidence.
- Small cohorts on different platforms, with batch heterogeneity.
- CXCL11 is sparse in single-cell data; detection is technically limited.
- Retrospective data with possible selection bias.

## Checklists
**TRIPOD+AI (prognostic model)**:
- data sources and participants
- outcome definition and time points
- handling of predictors
- sample-size considerations
- handling of missing data
- modelling approach and hyper-parameter tuning (nested CV)
- separation of training and evaluation data
- performance (discrimination, calibration, clinical utility)
- full model specification (coefficients or an accessible model file)
- fairness and intended scope
- code and data availability

**REMARK (biomarker)**:
- patient and specimen characteristics
- assay methods (here, expression platforms)
- study design
- pre-specified statistical analysis plan
- univariable and multivariable results
- cautious interpretation

Submit the completed checklists as supplementary material.

## AI-use statement template (adapt to the journal's format)
> During the preparation of this work the authors used AI agents to assist with code development, workflow automation and language editing: <list every tool and model actually used, with versions — e.g. Claude Code (Anthropic, model …) and the AIPOCH Open-Science workbench (v…, model …)>. The agent instructions (skill and specialist definitions) are openly available in the project repository (ai/). All analyses were executed with the open-source pipeline described in Methods, and all reported statistics were generated programmatically and traced to the pipeline outputs. The authors reviewed and verified all code, results and text and take full responsibility for the content of the publication. No generative-AI tools were used to create or alter images.

List exactly the tools that were used — no omissions and nothing unused. Check against the git history and Open-Science `.science` session records.

AI tools cannot be listed as authors.

## Data and code availability statement
> All datasets analysed are publicly available (accessions in Supplementary Table S1). The complete analysis pipeline and the interactive atlas source code are available at <GitHub URL> and archived at Zenodo (<DOI>). The interactive atlas is accessible at <URL>.

## Cover letter points
- The gap: the compartment balance of CXCL11 signalling has not been studied.
- Methodological rigour: multi-cohort validation, nested CV, a pre-specified analysis plan.
- Tool value: an open, interactive atlas and an open AI research layer.
- Fit with the journal's scope.

## Responding to reviewers
Point by point: quote the reviewer, give the response, then say where the manuscript changed (page and line); attach stats keys for any new analysis. Be courteous and specific; do not argue.
