# Track A: clinical / orthopaedic oncology.

GONOGO_COHORTS = config["params"]["go_no_go"]["cohorts"]


rule gonogo_cxcl11:
    """Gate 2: CXCL11 per-SD Cox HR + median-split KM in every verified cohort."""
    input:
        expand("data/processed/bulk/{c}.expr.parquet", c=GONOGO_COHORTS),
        expand("data/processed/bulk/{c}.clin.tsv", c=GONOGO_COHORTS),
    output:
        table="results/tables/gonogo_cxcl11.tsv",
        fig="results/figures/explore/gonogo_cxcl11.pdf",
        stats=stat_fragment("gonogo_cxcl11"),
    log:
        "logs/A/gonogo_cxcl11.log",
    shell:
        "python py/A_gonogo_cxcl11.py > {log} 2>&1"
