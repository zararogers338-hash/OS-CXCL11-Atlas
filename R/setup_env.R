# One-time bootstrap of the project R library (renv). Afterwards collaborators run
#   Rscript -e "renv::restore()"
# Run from the project root:  Rscript R/setup_env.R

options(repos = c(CRAN = "https://cloud.r-project.org"), renv.consent = TRUE)
if (!requireNamespace("renv", quietly = TRUE)) install.packages("renv")
if (!file.exists("renv/activate.R")) renv::init(bare = TRUE, restart = FALSE)
source("renv/activate.R")

pkgs <- c(
  # core
  "renv", "jsonlite", "yaml", "data.table", "readxl", "ggplot2", "patchwork", "ggrepel", "remotes", "BiocManager",
  # survival / clinical (track A)
  "survival", "survminer", "rms", "meta", "maxstat", "timeROC",
  # ML (convergence)
  "glmnet", "randomForestSRC",
  # bulk + immune (tracks B, C)
  "bioc::limma", "bioc::GEOquery", "bioc::sva", "bioc::GSVA", "bioc::ComplexHeatmap", "msigdbr",
  # immunotherapy / drugs (track D)
  "oncoPredict"
)
failed <- character()
for (p in pkgs) {
  ok <- tryCatch({ renv::install(p, prompt = FALSE); TRUE }, error = function(e) { message("FAILED ", p, ": ", conditionMessage(e)); FALSE })
  if (!ok) failed <- c(failed, p)
}
# IOBR (immune deconvolution suite) is GitHub-only and heavy; installed last.
ok <- tryCatch({ renv::install("IOBR/IOBR", prompt = FALSE); TRUE }, error = function(e) { message("FAILED IOBR: ", conditionMessage(e)); FALSE })
if (!ok) failed <- c(failed, "IOBR/IOBR")

renv::snapshot(prompt = FALSE, type = "all")
cat("\nR environment ready. Failed:", if (length(failed)) paste(failed, collapse = ", ") else "none", "\n")
