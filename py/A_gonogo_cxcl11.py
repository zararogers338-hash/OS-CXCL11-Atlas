"""Gate 2 Go/No-Go exploration: is CXCL11 associated with outcome, consistently across cohorts?

    python py/A_gonogo_cxcl11.py

For every harmonised cohort in data/processed/bulk/ (<ID>.expr.parquet + <ID>.clin.tsv):
  primary   : Cox HR per 1 SD of within-cohort z-scored CXCL11 (pre-specified)
  secondary : median split, Kaplan-Meier + log-rank
Endpoints: OS, EFS, MFS (whichever the cohort has). Axis genes (CXCL9/10, CXCR3, ACKR3)
are reported as exploratory context only.

Outputs: results/stats/gonogo_cxcl11.json, results/tables/gonogo_cxcl11.tsv,
         results/figures/explore/gonogo_cxcl11.{pdf,tiff,png}
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).parent))
from os_style import PALETTE, figsize, save_figure, use_style  # noqa: E402
from stats_registry import StatsFragment  # noqa: E402

warnings.filterwarnings("ignore")
BULK = Path("data/processed/bulk")
CFG = yaml.safe_load(Path("config/config.yaml").read_text(encoding="utf-8"))
ENDPOINTS = {"os": "OS", "efs": "EFS", "mfs": "MFS"}
GENES = ["CXCL11", "CXCL10", "CXCL9", "CXCR3", "ACKR3"]


def cohorts() -> list[str]:
    return sorted(p.name.removesuffix(".clin.tsv") for p in BULK.glob("*.clin.tsv")
                  if (BULK / p.name.replace(".clin.tsv", ".expr.parquet")).exists())


def cox_per_sd(df: pd.DataFrame, gene: str, ep: str) -> dict | None:
    from lifelines import CoxPHFitter
    d = df[[gene, f"{ep}_time_months", f"{ep}_event"]].dropna()
    d = d[d[f"{ep}_time_months"] > 0]
    if len(d) < CFG["params"]["qc"]["min_samples_per_cohort"] or d[f"{ep}_event"].sum() < 5:
        return None
    d = d.assign(z=(d[gene] - d[gene].mean()) / d[gene].std(ddof=1))
    cph = CoxPHFitter().fit(d[["z", f"{ep}_time_months", f"{ep}_event"]], f"{ep}_time_months", f"{ep}_event")
    s = cph.summary.loc["z"]
    return {"n": len(d), "events": int(d[f"{ep}_event"].sum()), "hr": float(s["exp(coef)"]),
            "lo": float(s["exp(coef) lower 95%"]), "hi": float(s["exp(coef) upper 95%"]), "p": float(s["p"])}


def km_median(df: pd.DataFrame, gene: str, ep: str):
    from lifelines.statistics import logrank_test
    d = df[[gene, f"{ep}_time_months", f"{ep}_event"]].dropna()
    d = d[d[f"{ep}_time_months"] > 0]
    high = d[gene] > d[gene].median()
    lr = logrank_test(d.loc[high, f"{ep}_time_months"], d.loc[~high, f"{ep}_time_months"],
                      d.loc[high, f"{ep}_event"], d.loc[~high, f"{ep}_event"])
    return d, high, float(lr.p_value)


def fmt_p(p: float) -> str:
    return f"{p:.1e}" if p < 0.001 else f"{p:.3f}"


def plot_km(ax, d, high, ep, p, title):
    from lifelines import KaplanMeierFitter
    t, e = d[f"{ep}_time_months"], d[f"{ep}_event"]
    for mask, label, color in [(high, "CXCL11 high", PALETTE["groups"]["high"]), (~high, "CXCL11 low", PALETTE["groups"]["low"])]:
        kmf = KaplanMeierFitter().fit(t[mask], e[mask], label=f"{label} (n={mask.sum()})")
        kmf.plot_survival_function(ax=ax, ci_show=False, color=color, linewidth=1.0, show_censors=True,
                                   censor_styles={"ms": 3, "marker": "|", "mew": 0.6})
    ax.set_xlim(0, 120)
    ax.set_xticks([0, 30, 60, 90, 120])
    ax.set_ylim(0, 1.02)
    ax.set_xlabel("Months")
    ax.set_ylabel(f"{ENDPOINTS[ep]} probability")
    ax.set_title(title, loc="left")
    ax.text(0.97, 0.97, f"log-rank P = {fmt_p(p)}", transform=ax.transAxes, ha="right", va="top", fontsize=7,
            color=PALETTE["ink"]["secondary"])
    ax.legend(loc="lower left", fontsize=6.5, handlelength=1.2, borderaxespad=0.2)
    ax.grid(axis="y", color=PALETTE["ink"]["grid"], linewidth=0.3)


def plot_forest(ax, rows: pd.DataFrame, title: str):
    from matplotlib.ticker import FixedLocator, NullLocator
    rows = rows.iloc[::-1].reset_index(drop=True)
    color = PALETTE["entity"]["CXCL11"]
    ax.axvline(1, color=PALETTE["ink"]["axis"], linewidth=0.6, linestyle="--")
    for i, r in rows.iterrows():
        ax.plot([r.lo, r.hi], [i, i], color=color, linewidth=1.0, solid_capstyle="round")
        ax.plot(r.hr, i, "s", color=color, ms=4)
    ax.set_xscale("log")
    ax.xaxis.set_major_locator(FixedLocator([0.25, 0.5, 1, 2, 4]))
    ax.xaxis.set_minor_locator(NullLocator())
    ax.set_xticklabels(["0.25", "0.5", "1", "2", "4"])
    lo, hi = min(rows.lo.min(), 0.4), max(rows.hi.max(), 1.6)
    ax.set_xlim(lo * 0.85, hi * 1.15)
    ax.set_ylim(-0.6, len(rows) - 0.4)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([f"{r.cohort} · {ENDPOINTS[r.endpoint]}\nn={r.n}, events={r.events}" for r in rows.itertuples()],
                       fontsize=6.5)
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    # Right-hand column of estimates as tick labels of a twin axis, so layout accounts for it.
    right = ax.twinx()
    right.set_ylim(ax.get_ylim())
    right.set_yticks(range(len(rows)))
    right.set_yticklabels([f"{r.hr:.2f} ({r.lo:.2f}–{r.hi:.2f})\nP = {fmt_p(r.p)}" for r in rows.itertuples()],
                          fontsize=6.5, color=PALETTE["ink"]["secondary"])
    right.tick_params(axis="y", length=0)
    right.spines["right"].set_visible(False)
    ax.set_xlabel("HR per 1 SD CXCL11")
    ax.set_title(title, loc="left")


def main() -> int:
    import matplotlib.pyplot as plt
    use_style()
    results, km_panels = [], []
    for cid in cohorts():
        expr = pd.read_parquet(BULK / f"{cid}.expr.parquet")
        clin = pd.read_csv(BULK / f"{cid}.clin.tsv", sep="\t", index_col=0)
        genes = [g for g in GENES if g in expr.index]
        df = clin.join(expr.loc[genes].T, how="inner")
        for ep in ENDPOINTS:
            if f"{ep}_time_months" not in df or df[f"{ep}_event"].notna().sum() == 0:
                continue
            for g in genes:
                r = cox_per_sd(df, g, ep)
                if r is None:
                    continue
                _, high, p_lr = km_median(df, g, ep)
                results.append({"cohort": cid, "endpoint": ep, "gene": g, **r, "logrank_p": p_lr})
            if "CXCL11" in genes and cid == "TARGET-OS" and ep in ("os", "efs"):
                d, high, p_lr = km_median(df, "CXCL11", ep)
                km_panels.append((d, high, ep, p_lr, f"TARGET-OS · {ENDPOINTS[ep]} by CXCL11"))

    res = pd.DataFrame(results)
    res.insert(2, "analysis", np.where(res.gene == "CXCL11", "primary (pre-specified)", "exploratory"))
    res["q_bh_exploratory"] = np.nan
    explo = res.analysis == "exploratory"
    if explo.any():
        p = res.loc[explo, "p"].to_numpy(); order = np.argsort(p); m = len(p)
        q = np.minimum.accumulate((p[order] * m / np.arange(1, m + 1))[::-1])[::-1]
        res.loc[res.index[explo][order], "q_bh_exploratory"] = np.minimum(q, 1.0)
    Path("results/tables").mkdir(parents=True, exist_ok=True)
    res.to_csv("results/tables/gonogo_cxcl11.tsv", sep="\t", index=False)
    main_rows = res[res.gene == "CXCL11"].reset_index(drop=True)

    with StatsFragment("gonogo_cxcl11") as st:
        for r in main_rows.itertuples():
            key = f"gonogo_{r.cohort.lower().replace('-', '')}_{r.endpoint}_cxcl11"
            st.record(f"{key}_hr", r.hr, display=f"{r.hr:.2f}", ci=(round(r.lo, 2), round(r.hi, 2)), n=r.n,
                      desc=f"{r.cohort} {ENDPOINTS[r.endpoint]}: HR per 1 SD CXCL11 (Cox, exploratory gate)")
            st.record(f"{key}_p", r.p, display=fmt_p(r.p), desc=f"{r.cohort} {ENDPOINTS[r.endpoint]}: Wald P for CXCL11 per SD")
            st.record(f"{key}_events", r.events, desc=f"{r.cohort} {ENDPOINTS[r.endpoint]}: events")
        n_coh = main_rows.cohort.nunique()
        st.record("gonogo_n_cohorts", n_coh, desc="cohorts with evaluable CXCL11 survival analysis")

    # Row 1: KM panels; row 2: forest plot across every cohort/endpoint (grows with cohorts).
    forest_h = 14 + 9 * len(main_rows)
    fig = plt.figure(figsize=figsize("double", 62 + forest_h))
    gs = fig.add_gridspec(2, max(len(km_panels), 1), height_ratios=[62, forest_h])
    tags = iter("abcdef")
    for j, panel in enumerate(km_panels):
        d, high, ep, p, title = panel
        plot_km(fig.add_subplot(gs[0, j]), d, high, ep, p, f"{next(tags)}   {title}")
    plot_forest(fig.add_subplot(gs[1, :]), main_rows, f"{next(tags)}   CXCL11 per-SD hazard ratio (Cox) — exploratory, cohorts analysed so far: {main_rows.cohort.nunique()}")
    out = save_figure(fig, "results/figures/explore/gonogo_cxcl11", formats=("pdf", "tiff", "png"))

    print(main_rows[["cohort", "endpoint", "n", "events", "hr", "lo", "hi", "p", "logrank_p"]].round(4).to_string(index=False))
    print("\nexploratory axis genes:")
    print(res[res.gene != "CXCL11"][["cohort", "endpoint", "gene", "hr", "lo", "hi", "p"]].round(4).to_string(index=False))
    print(f"\nfigure -> {out}.pdf / .png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
