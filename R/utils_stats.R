# R twin of py/stats_registry.py: each script writes one fragment to
# results/stats/<fragment>.json; Snakemake's collect_stats rule merges them.
#
#   st <- stats_fragment("A_clinical_km", source = "R/A_clinical_km.R")
#   st <- stats_record(st, "os_target_hr", 1.84, display = "1.84", ci = c(1.12, 3.02),
#                      desc = "TARGET-OS OS hazard ratio, CXCL11 high vs low")
#   stats_write(st)

stats_fragment <- function(name, source) {
  stopifnot(grepl("^[a-z0-9_]+$", tolower(name)))
  list(name = name, source = source, stats = list())
}

stats_record <- function(st, key, value, desc, display = NULL, ci = NULL, n = NULL) {
  stopifnot(grepl("^[a-z0-9_]+$", key))
  if (!is.null(st$stats[[key]])) stop("duplicate stat key in fragment ", st$name, ": ", key)
  if (is.null(display)) {
    display <- if (is.numeric(value) && value != 0 && abs(value) < 0.001) {
      formatC(value, format = "e", digits = 1)
    } else if (is.numeric(value)) {
      format(signif(value, 3))
    } else {
      as.character(value)
    }
  }
  st$stats[[key]] <- list(value = value, display = display, ci = ci, n = n,
                          desc = desc, source = st$source, fragment = st$name)
  st
}

stats_write <- function(st, dir = file.path("results", "stats")) {
  dir.create(dir, recursive = TRUE, showWarnings = FALSE)
  path <- file.path(dir, paste0(st$name, ".json"))
  payload <- list(fragment = st$name,
                  written = format(Sys.time(), tz = "UTC", usetz = TRUE),
                  stats = st$stats)
  jsonlite::write_json(payload, path, auto_unbox = TRUE, null = "null", digits = NA, pretty = TRUE)
  invisible(path)
}
