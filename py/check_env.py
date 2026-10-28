"""Check the analysis environment, grouped by pipeline stage.

    python py/check_env.py            # all groups
    python py/check_env.py core bulk  # selected groups
Exit code 1 if anything in the selected groups is missing.
"""
from __future__ import annotations

import glob
import importlib.util
import os
import shutil
import subprocess
import sys

PY_GROUPS = {
    "core": ["snakemake", "pandas", "numpy", "scipy", "yaml", "requests", "pyarrow", "matplotlib"],
    "singlecell": ["scanpy", "anndata", "harmonypy", "decoupler"],
    "ml": ["sklearn", "sksurv", "lifelines", "shap"],
    "app": ["streamlit", "plotly"],
}
R_GROUPS = {
    "core": ["jsonlite", "ggplot2", "patchwork", "data.table", "renv"],
    "bulk": ["limma", "GEOquery", "sva", "GSVA", "survival", "survminer", "rms", "meta", "IOBR"],
    "immunotherapy": ["oncoPredict"],
}
TOOLS = {"core": ["git"], "manuscript": ["quarto"]}


def find_rscript() -> str | None:
    hit = shutil.which("Rscript")
    if hit:
        return hit
    cands = sorted(glob.glob(r"C:\Program Files\R\R-*\bin\Rscript.exe")
                   + glob.glob(os.path.expandvars(r"%LOCALAPPDATA%\Programs\R\R-*\bin\Rscript.exe")))
    return cands[-1] if cands else None


def find_tool(name: str) -> str | None:
    return shutil.which(name) or next(iter(glob.glob(os.path.expandvars(rf"%LOCALAPPDATA%\Programs\{name}\bin\{name}.exe"))), None)


R_ENV = dict(os.environ, RENV_CONFIG_SYNCHRONIZED_CHECK="FALSE")  # renv startup chatter goes to stdout


def run_r(rscript: str, expr: str, *args: str) -> str:
    return subprocess.run([rscript, "-e", expr, *args], capture_output=True, text=True, timeout=300, env=R_ENV).stdout


def check_r(pkgs: list[str], rscript: str) -> dict[str, bool]:
    expr = "pk <- commandArgs(TRUE); cat(paste0('@@', pk, '=', vapply(pk, requireNamespace, logical(1), quietly = TRUE)), sep = '\\n')"
    out = run_r(rscript, expr, *pkgs)
    status = dict(line[2:].split("=", 1) for line in out.splitlines() if line.startswith("@@"))
    return {p: status.get(p) == "TRUE" for p in pkgs}


def main(groups: list[str]) -> int:
    groups = groups or sorted(set(PY_GROUPS) | set(R_GROUPS) | set(TOOLS))
    rows: list[tuple[str, str, str, bool]] = []
    rows.append(("core", "python", sys.version.split()[0], sys.version_info >= (3, 11)))
    for g in groups:
        for mod in PY_GROUPS.get(g, []):
            rows.append((g, f"py:{mod}", "", importlib.util.find_spec(mod) is not None))
        for tool in TOOLS.get(g, []):
            path = find_tool(tool)
            rows.append((g, f"tool:{tool}", path or "", path is not None))
    rscript = find_rscript()
    r_needed = [g for g in groups if g in R_GROUPS]
    if r_needed:
        if not rscript:
            rows.append(("core", "R (Rscript)", "not found", False))
        else:
            out = run_r(rscript, "cat('@@', as.character(getRversion()), sep = '')")
            ver = next((line[2:] for line in out.splitlines() if line.startswith("@@")), "0.0")
            rows.append(("core", "R", ver, tuple(map(int, ver.split(".")[:2])) >= (4, 5)))
            for g in r_needed:
                for pkg, ok in check_r(R_GROUPS[g], rscript).items():
                    rows.append((g, f"R:{pkg}", "", ok))
    width = max(len(r[1]) for r in rows)
    for g, name, info, ok in rows:
        print(f"[{'OK' if ok else 'MISSING':7}] {g:13} {name:<{width}} {info}")
    missing = [r for r in rows if not r[3]]
    print(f"\n{len(rows) - len(missing)}/{len(rows)} OK" + (f"; missing: {', '.join(r[1] for r in missing)}" if missing else ""))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
