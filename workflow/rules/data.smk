# Stage 1: data acquisition and harmonisation.


rule fetch_geo_bulk:
    output:
        "data/raw/geo/{gse}/manifest.json",
    wildcard_constraints:
        gse=r"GSE\d+",
    log:
        "logs/fetch/{gse}.log",
    shell:
        "python -u py/fetch_geo.py {wildcards.gse} --out data/raw/geo --retries 3 > {log} 2>&1"


rule fetch_target_os:
    output:
        "data/raw/target_os/manifest.json",
    log:
        "logs/fetch/target_os.log",
    shell:
        "python -u py/fetch_target.py --out data/raw/target_os > {log} 2>&1"


rule prep_target_os:
    input:
        "data/raw/target_os/manifest.json",
    output:
        expr="data/processed/bulk/TARGET-OS.expr.parquet",
        clin="data/processed/bulk/TARGET-OS.clin.tsv",
        stats=stat_fragment("data_target_os"),
    log:
        "logs/prep/target_os.log",
    shell:
        "python py/prep_target.py > {log} 2>&1"


rule prep_geo_bulk:
    input:
        "data/raw/geo/{gse}/manifest.json",
    output:
        expr="data/processed/bulk/{gse}.expr.parquet",
        clin="data/processed/bulk/{gse}.clin.tsv",
    wildcard_constraints:
        gse=r"GSE\d+",
    log:
        "logs/prep/{gse}.log",
    shell:
        "python py/prep_geo.py {wildcards.gse} > {log} 2>&1"
