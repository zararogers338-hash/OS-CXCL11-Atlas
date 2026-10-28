"""Harmonise a GEO bulk cohort: series matrix -> gene-level matrix + standard clinical table.

    python py/prep_geo.py GSE21257 --inspect     # print sample characteristics to design the mapper
    python py/prep_geo.py GSE21257               # write data/processed/bulk/GSE21257.{expr.parquet,clin.tsv}

Clinical fields differ per series, so each cohort needs an explicit mapper in CLINICAL_MAPPERS,
written only after inspecting the real characteristics (never from memory) and documented in
docs/data_cards/<GSE>.md.
"""
from __future__ import annotations

import argparse
import gzip
import re
import sys
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from stats_registry import StatsFragment  # noqa: E402

RAW = Path("data/raw/geo")
OUT = Path("data/processed/bulk")
SYMBOL_COLUMNS = ["Symbol", "Gene Symbol", "GENE_SYMBOL", "ILMN_Gene", "SYMBOL", "gene_symbol", "Gene symbol"]


def parse_series_matrix(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (expression probes x GSM, sample metadata GSM x fields)."""
    meta: dict[str, list[list[str]]] = {}
    table_lines: list[str] = []
    in_table = False
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("!series_matrix_table_begin"):
                in_table = True
                continue
            if line.startswith("!series_matrix_table_end"):
                break
            if in_table:
                table_lines.append(line)
            elif line.startswith("!Sample_"):
                key, *vals = line.rstrip("\n").split("\t")
                meta.setdefault(key[len("!Sample_"):], []).append([v.strip('"') for v in vals])
    from io import StringIO
    expr = pd.read_csv(StringIO("".join(table_lines)), sep="\t", index_col=0, quotechar='"')
    gsm = meta["geo_accession"][0]
    samples = pd.DataFrame(index=gsm)
    for key, rows in meta.items():
        if key.startswith("characteristics"):
            for row in rows:  # one row per characteristic slot; values are "key: value"
                for g, v in zip(gsm, row):
                    if ":" in v:
                        k, val = v.split(":", 1)
                        samples.loc[g, f"ch_{k.strip().lower().replace(' ', '_')}"] = val.strip()
        elif len(rows) == 1 and key in {"title", "source_name_ch1", "platform_id", "description"}:
            samples[key] = rows[0]
    return expr, samples


def load_platform(path: Path) -> pd.Series:
    """Probe ID -> gene symbol from an NCBI GPL full-text table."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        lines = fh.read().splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("!platform_table_begin")) + 1
    end = next((i for i, l in enumerate(lines) if l.startswith("!platform_table_end")), len(lines))
    from io import StringIO
    tab = pd.read_csv(StringIO("\n".join(lines[start:end])), sep="\t", dtype=str, quotechar='"')
    col = next((c for c in SYMBOL_COLUMNS if c in tab.columns), None)
    if col is None:
        raise KeyError(f"no gene-symbol column in {path.name}: {list(tab.columns)}")
    sym = tab.set_index(tab.columns[0])[col].str.split(r"\s*///\s*").str[0].str.strip()
    return sym[sym.notna() & (sym != "") & (sym != "---")]


def to_gene_matrix(expr: pd.DataFrame, symbols: pd.Series) -> tuple[pd.DataFrame, bool]:
    expr = expr.apply(pd.to_numeric, errors="coerce")
    logged = True
    if np.nanmax(expr.values) > 50:  # not on log scale yet
        expr = np.log2(expr.clip(lower=0) + 1)
        logged = False
    expr.index = expr.index.astype(str).map(symbols)
    expr = expr[expr.index.notna()]
    expr = expr.assign(_m=expr.mean(axis=1)).sort_values("_m", ascending=False)
    expr = expr[~expr.index.duplicated(keep="first")].drop(columns="_m")
    return expr, logged


# Cohort-specific clinical mappers: samples DataFrame -> standard clinical DataFrame
# (index = GSM; columns from references/datasets.md). Add one per cohort after --inspect.
CLINICAL_MAPPERS: dict[str, Callable[[pd.DataFrame], pd.DataFrame]] = {}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gse")
    ap.add_argument("--inspect", action="store_true")
    args = ap.parse_args(argv)
    src = RAW / args.gse
    matrices = sorted(src.glob("*_series_matrix.txt.gz"))
    if not matrices:
        sys.exit(f"no series matrix in {src}; run py/fetch_geo.py {args.gse} first")
    parts = [parse_series_matrix(m) for m in matrices]
    samples = pd.concat([s for _, s in parts])
    if args.inspect:
        pd.set_option("display.width", 220, "display.max_columns", 50, "display.max_colwidth", 40)
        print(f"{args.gse}: {len(samples)} samples, matrices: {[m.name for m in matrices]}")
        for c in samples.columns:
            vals = samples[c].value_counts(dropna=False)
            print(f"\n[{c}] {vals.size} distinct" + ("" if vals.size > 15 else f": {vals.to_dict()}"))
            if vals.size > 15:
                print("  e.g.", list(samples[c].dropna().unique()[:6]))
        return 0
    if args.gse not in CLINICAL_MAPPERS:
        sys.exit(f"no clinical mapper for {args.gse}: run --inspect, then add one to CLINICAL_MAPPERS")
    exprs = []
    for (expr, s), m in zip(parts, matrices):
        gpl = s["platform_id"].iloc[0]
        g, logged = to_gene_matrix(expr, load_platform(src / f"{gpl}.annot.txt"))
        print(f"{m.name}: {gpl}, {g.shape[0]} genes x {g.shape[1]} samples, {'already log' if logged else 'log2-transformed'}")
        exprs.append(g)
    expr = pd.concat(exprs, axis=1, join="inner")
    clin = CLINICAL_MAPPERS[args.gse](samples)
    keep = [s for s in clin.index if s in expr.columns]
    OUT.mkdir(parents=True, exist_ok=True)
    expr[keep].astype("float32").to_parquet(OUT / f"{args.gse}.expr.parquet")
    clin.loc[keep].assign(cohort=args.gse).to_csv(OUT / f"{args.gse}.clin.tsv", sep="\t")
    key = re.sub(r"\W", "", args.gse.lower())
    with StatsFragment(f"data_{key}") as st:
        st.record(f"{key}_n_samples", len(keep), desc=f"{args.gse} tumour samples analysed")
        for ep in ("os", "efs", "mfs"):
            if f"{ep}_event" in clin:
                ok = clin.loc[keep, [f"{ep}_time_months", f"{ep}_event"]].dropna()
                st.record(f"{key}_n_{ep}", len(ok), desc=f"{args.gse} samples with {ep.upper()} data")
                st.record(f"{key}_{ep}_events", int(ok[f"{ep}_event"].sum()), desc=f"{args.gse} {ep.upper()} events")
    print(f"-> {OUT / args.gse}.expr.parquet ({len(keep)} samples), clin.tsv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
