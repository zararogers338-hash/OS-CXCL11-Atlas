"""Harmonise TARGET-OS: expression (log2 TPM+1, gene symbols, primary tumours only) + clinical.

    python py/prep_target.py

Inputs : data/raw/target_os/ (see fetch_target.py)
Outputs: data/processed/bulk/TARGET-OS.expr.parquet  (genes x patients)
         data/processed/bulk/TARGET-OS.clin.tsv       (standard clinical fields)
         results/stats/data_target_os.json
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from stats_registry import StatsFragment  # noqa: E402

RAW = Path("data/raw/target_os")
OUT = Path("data/processed/bulk")
DAYS_PER_MONTH = 30.4375
EFS_CENSORED = {"censored", "none"}


def load_expression() -> pd.DataFrame:
    expr = pd.read_csv(RAW / "TARGET-OS.star_tpm.tsv.gz", sep="\t", index_col=0)
    probemap = pd.read_csv(RAW / "gencode.v36.annotation.gtf.gene.probemap", sep="\t", usecols=["id", "gene"])
    expr.index = expr.index.map(probemap.set_index("id")["gene"])
    expr = expr[expr.index.notna()]
    # Collapse duplicated symbols: keep the row with the highest mean expression.
    expr = expr.assign(_mean=expr.mean(axis=1)).sort_values("_mean", ascending=False)
    expr = expr[~expr.index.duplicated(keep="first")].drop(columns="_mean")
    return expr


def primary_tumour_columns(cols: pd.Index) -> dict[str, str]:
    """Map sample barcodes (TARGET-40-XXXXXX-01A) to patient USI, primary tumours (01) only."""
    keep: dict[str, str] = {}
    for c in sorted(cols):
        parts = c.split("-")
        if len(parts) >= 4 and parts[3][:2] == "01":
            keep.setdefault("-".join(parts[:3]), c)
    return {sample: usi for usi, sample in keep.items()}


def load_clinical() -> pd.DataFrame:
    frames = []
    for f in sorted((RAW / "clinical").glob("TARGET_OS_ClinicalData_*.xlsx")):
        if "Percent_Tumor" in f.name:
            continue
        df = pd.read_excel(f, sheet_name="Clinical Data")
        df["_source"] = f.name
        frames.append(df)
    clin = pd.concat(frames, ignore_index=True)
    clin["_nonnull"] = clin.notna().sum(axis=1)
    clin = clin.sort_values("_nonnull", ascending=False).drop_duplicates("TARGET USI")
    first_event = clin["First Event"].astype("string").str.strip().str.lower()
    vital = clin["Vital Status"].astype("string").str.strip().str.lower()
    dx = clin["Disease at diagnosis"].astype("string").str.lower()

    def flag(mask: pd.Series) -> np.ndarray:
        return mask.fillna(False).to_numpy(dtype=bool)

    std = pd.DataFrame({
        "patient_id": clin["TARGET USI"],
        "age": clin["Age at Diagnosis in Days"] / 365.25,
        "sex": clin["Gender"].astype("string").str.strip().str.lower(),
        "site": clin["Primary tumor site"],
        "metastasis_dx": np.where(flag(dx.str.startswith("metastatic")), 1.0,
                                  np.where(flag(dx.str.startswith("non-metastatic")), 0.0, np.nan)),
        "histologic_response": clin["Histologic response"],
        "os_time_months": clin["Overall Survival Time in Days"] / DAYS_PER_MONTH,
        "os_event": np.where(flag(vital == "dead"), 1.0, np.where(flag(vital == "alive"), 0.0, np.nan)),
        "efs_time_months": clin["Event Free Survival Time in Days"] / DAYS_PER_MONTH,
        # Blank "First Event" with an EFS time = event-free follow-up (verified: all such
        # patients are alive with EFS time == OS time), so it is coded as censored.
        "efs_event": np.where(flag(first_event.isna()),
                              np.where(clin["Event Free Survival Time in Days"].notna(), 0.0, np.nan),
                              (~flag(first_event.isin(EFS_CENSORED))).astype(float)),
        "first_event_raw": clin["First Event"],
        "clinical_source": clin["_source"],
        "cohort": "TARGET-OS",
    })
    return std.set_index("patient_id")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    expr_all = load_expression()
    mapping = primary_tumour_columns(expr_all.columns)
    expr = expr_all[list(mapping)].rename(columns=mapping)
    clin = load_clinical()
    clin = clin.reindex(expr.columns)
    clin.index.name = "patient_id"

    print("First Event values:", clin["first_event_raw"].value_counts(dropna=False).to_dict())
    print("Histologic response:", clin["histologic_response"].value_counts(dropna=False).to_dict())

    expr.astype("float32").to_parquet(OUT / "TARGET-OS.expr.parquet")
    clin.to_csv(OUT / "TARGET-OS.clin.tsv", sep="\t")

    os_ok = clin["os_time_months"].notna() & clin["os_event"].notna()
    efs_ok = clin["efs_time_months"].notna() & clin["efs_event"].notna()
    with StatsFragment("data_target_os") as st:
        st.record("target_n_expr_samples", int(expr_all.shape[1]), desc="TARGET-OS RNA-seq samples (all types)")
        st.record("target_n_primary", int(expr.shape[1]), desc="TARGET-OS primary-tumour patients with RNA-seq")
        st.record("target_n_genes", int(expr.shape[0]), desc="TARGET-OS genes after symbol collapse")
        st.record("target_n_os", int(os_ok.sum()), desc="TARGET-OS patients with OS data")
        st.record("target_os_events", int(clin.loc[os_ok, "os_event"].sum()), desc="TARGET-OS deaths")
        st.record("target_n_efs", int(efs_ok.sum()), desc="TARGET-OS patients with EFS data")
        st.record("target_efs_events", int(clin.loc[efs_ok, "efs_event"].sum()), desc="TARGET-OS EFS events")
        st.record("target_n_metastatic_dx", int((clin["metastasis_dx"] == 1).sum()), desc="TARGET-OS metastatic at diagnosis")
    print(f"expression: {expr_all.shape[1]} samples -> {expr.shape[1]} primary patients x {expr.shape[0]} genes")
    print(f"OS: n={os_ok.sum()} events={int(clin.loc[os_ok, 'os_event'].sum())}; "
          f"EFS: n={efs_ok.sum()} events={int(clin.loc[efs_ok, 'efs_event'].sum())}; "
          f"metastatic at dx: {(clin['metastasis_dx'] == 1).sum()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
