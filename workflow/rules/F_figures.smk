# Figure assembly (hand-built schematics + multi-panel figures).


rule fig1_study_design:
    """Study design + three-compartment hypothesis; sample sizes come from stats.json."""
    input:
        "results/stats.json",
        "style/palette.json",
    output:
        "results/figures/fig1_study_design.pdf",
        "results/figures/fig1_study_design.tiff",
        "results/figures/fig1_study_design.png",
    log:
        "logs/F/fig1_study_design.log",
    shell:
        "python py/F_fig1_study_design.py > {log} 2>&1"
