# Marrow visual system for ggplot2. Every colour comes from style/palette.json.
#
#   source("style/theme_os.R")
#   p + theme_os() + scale_colour_os_groups()
#   os_save(p, "results/figures/fig2a_km", width = "single", height_mm = 60)

suppressPackageStartupMessages({
  library(ggplot2)
  library(jsonlite)
})

os_palette <- function(path = file.path("style", "palette.json")) {
  jsonlite::fromJSON(path, simplifyVector = TRUE)
}

.os <- os_palette()

theme_os <- function(base_size = .os$font$base_pt, base_family = .os$font$family, grid = "y") {
  ink <- .os$ink
  t <- theme_classic(base_size = base_size, base_family = base_family) +
    theme(
      text = element_text(colour = ink$primary),
      axis.text = element_text(colour = ink$secondary, size = base_size),
      axis.title = element_text(colour = ink$primary, size = base_size),
      axis.line = element_line(colour = ink$axis, linewidth = 0.3),
      axis.ticks = element_line(colour = ink$axis, linewidth = 0.3),
      axis.ticks.length = unit(1.2, "mm"),
      plot.title = element_text(size = .os$font$title_pt, face = "bold", hjust = 0),
      plot.subtitle = element_text(colour = ink$secondary, size = base_size),
      plot.tag = element_text(size = .os$font$title_pt + 1, face = "bold"),
      legend.title = element_text(size = base_size),
      legend.text = element_text(size = base_size, colour = ink$secondary),
      legend.key.size = unit(3, "mm"),
      legend.background = element_blank(),
      strip.background = element_rect(fill = .os$surfaces$panel, colour = NA),
      strip.text = element_text(size = base_size, face = "bold"),
      panel.background = element_rect(fill = .os$surfaces$figure, colour = NA),
      plot.background = element_rect(fill = .os$surfaces$figure, colour = NA),
      plot.margin = margin(2, 2, 2, 2, "mm")
    )
  grid_line <- element_line(colour = ink$grid, linewidth = 0.25)
  if (grid %in% c("y", "xy")) t <- t + theme(panel.grid.major.y = grid_line)
  if (grid %in% c("x", "xy")) t <- t + theme(panel.grid.major.x = grid_line)
  t
}

os_entity_colours <- function() unlist(.os$entity)

scale_colour_os_entity <- function(...) scale_colour_manual(values = os_entity_colours(), ...)
scale_fill_os_entity <- function(...) scale_fill_manual(values = os_entity_colours(), ...)

scale_colour_os_groups <- function(...) scale_colour_manual(values = unlist(.os$groups), ...)
scale_fill_os_groups <- function(...) scale_fill_manual(values = unlist(.os$groups), ...)

scale_colour_os_seq <- function(...) scale_colour_gradientn(colours = .os$sequential$crimson, ...)
scale_fill_os_seq <- function(...) scale_fill_gradientn(colours = .os$sequential$crimson, ...)

os_diverging_colours <- function() c(.os$diverging$negative, .os$diverging$mid, .os$diverging$positive)
scale_fill_os_div <- function(limits = c(-1, 1), ...) {
  scale_fill_gradientn(colours = os_diverging_colours(), limits = limits, ...)
}
scale_colour_os_div <- function(limits = c(-1, 1), ...) {
  scale_colour_gradientn(colours = os_diverging_colours(), limits = limits, ...)
}

# Save a figure as vector PDF + 600-dpi LZW TIFF at journal widths.
os_save <- function(plot, path_no_ext, width = c("single", "onehalf", "double"), height_mm = 60) {
  width <- match.arg(width)
  w_mm <- .os$size_mm[[width]]
  stopifnot(height_mm <= .os$size_mm$max_height)
  dir.create(dirname(path_no_ext), recursive = TRUE, showWarnings = FALSE)
  ggsave(paste0(path_no_ext, ".pdf"), plot, width = w_mm, height = height_mm, units = "mm",
         device = cairo_pdf)
  ggsave(paste0(path_no_ext, ".tiff"), plot, width = w_mm, height = height_mm, units = "mm",
         dpi = .os$export$dpi, compression = "lzw")
  invisible(path_no_ext)
}
