from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
FIGURES = ROOT / "figures"

MINE_WIDE = PROCESSED / "mine_related_stations_wide.csv"

PARAMETERS = ["lead", "zinc", "copper", "calcium", "ph"]
CORRELATION_PAIRS = [
    ("lead", "zinc"),
    ("zinc", "copper"),
    ("lead", "copper"),
    ("lead", "ph"),
    ("zinc", "ph"),
    ("copper", "ph"),
    ("calcium", "ph"),
    ("lead", "calcium"),
    ("zinc", "calcium"),
    ("copper", "calcium"),
]
RATIO_SPECS = {
    "lead_to_zinc": ("lead", "zinc"),
    "copper_to_zinc": ("copper", "zinc"),
    "lead_to_calcium": ("lead", "calcium"),
    "zinc_to_calcium": ("zinc", "calcium"),
    "copper_to_calcium": ("copper", "calcium"),
}


def load_mine_data() -> pd.DataFrame:
    return pd.read_csv(MINE_WIDE, parse_dates=["sample_date"], low_memory=False)


def parameter_coverage(data: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for parameter in PARAMETERS + ["hardness"]:
        subset = data[data[parameter].notna()]
        rows.append(
            {
                "parameter": parameter,
                "n_records": len(subset),
                "n_stations": subset["station_id"].nunique(),
                "first_date": subset["sample_date"].min(),
                "last_date": subset["sample_date"].max(),
                "median": subset[parameter].median(),
                "minimum": subset[parameter].min(),
                "maximum": subset[parameter].max(),
            }
        )
    return pd.DataFrame(rows)


def paired_data(data: pd.DataFrame, left: str, right: str) -> pd.DataFrame:
    pair = data[[left, right]].dropna().copy()
    if left != "ph":
        pair = pair[pair[left] > 0]
    if right != "ph":
        pair = pair[pair[right] > 0]
    return pair


def correlation_table(data: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for left, right in CORRELATION_PAIRS:
        pair = paired_data(data, left, right)
        if len(pair) < 5:
            rows.append(
                {
                    "parameter_1": left,
                    "parameter_2": right,
                    "n_paired_samples": len(pair),
                    "pearson_r": np.nan,
                    "pearson_p": np.nan,
                    "spearman_r": np.nan,
                    "spearman_p": np.nan,
                }
            )
            continue
        pearson = stats.pearsonr(pair[left], pair[right])
        spearman = stats.spearmanr(pair[left], pair[right])
        rows.append(
            {
                "parameter_1": left,
                "parameter_2": right,
                "n_paired_samples": len(pair),
                "pearson_r": pearson.statistic,
                "pearson_p": pearson.pvalue,
                "spearman_r": spearman.statistic,
                "spearman_p": spearman.pvalue,
            }
        )
    return pd.DataFrame(rows).sort_values("n_paired_samples", ascending=False)


def add_ratios(data: pd.DataFrame) -> pd.DataFrame:
    data = data.copy()
    for ratio_name, (numerator, denominator) in RATIO_SPECS.items():
        valid = data[numerator].notna() & data[denominator].notna() & (data[denominator] > 0)
        data[ratio_name] = np.nan
        data.loc[valid, ratio_name] = data.loc[valid, numerator] / data.loc[valid, denominator]
    return data


def ratio_summary(data: pd.DataFrame, group_col: str | None = None) -> pd.DataFrame:
    ratio_cols = list(RATIO_SPECS)
    rows = []
    if group_col is None:
        groups = [("all_mine_related", data)]
    else:
        groups = list(data.groupby(group_col, dropna=False))

    for group_name, group in groups:
        for ratio in ratio_cols:
            values = group[ratio].replace([np.inf, -np.inf], np.nan).dropna()
            values = values[values > 0]
            if values.empty:
                continue
            rows.append(
                {
                    "group": group_name,
                    "ratio": ratio,
                    "n_samples": len(values),
                    "n_stations": group.loc[values.index, "station_id"].nunique(),
                    "median": values.median(),
                    "q25": values.quantile(0.25),
                    "q75": values.quantile(0.75),
                    "minimum": values.min(),
                    "maximum": values.max(),
                }
            )
    return pd.DataFrame(rows)


def plot_correlation_heatmap(data: pd.DataFrame) -> None:
    corr = data[PARAMETERS].corr(method="spearman", min_periods=5)
    plt.figure(figsize=(8, 7))
    sns.heatmap(corr, annot=True, cmap="vlag", center=0, vmin=-1, vmax=1, square=True)
    plt.title("Mine-related stations: Spearman correlation")
    plt.tight_layout()
    plt.savefig(FIGURES / "mine_related_spearman_heatmap.png", dpi=220)
    plt.close()


def plot_scatterplots(data: pd.DataFrame) -> None:
    pairs = [("lead", "zinc"), ("zinc", "copper"), ("ph", "zinc"), ("ph", "lead")]
    fig, axes = plt.subplots(1, len(pairs), figsize=(5 * len(pairs), 4))
    for ax, (left, right) in zip(axes, pairs, strict=False):
        pair = paired_data(data, left, right)
        if len(pair) > 8000:
            pair = pair.sample(n=8000, random_state=42)
        sns.scatterplot(data=pair, x=left, y=right, s=13, alpha=0.45, linewidth=0, ax=ax)
        if left != "ph":
            ax.set_xscale("log")
        if right != "ph":
            ax.set_yscale("log")
        ax.set_title(f"{left} vs {right}")
    plt.tight_layout()
    plt.savefig(FIGURES / "mine_related_key_scatterplots.png", dpi=220)
    plt.close(fig)


def plot_ratio_boxplots(data: pd.DataFrame) -> None:
    ratio_cols = list(RATIO_SPECS)
    ratio_long = data.melt(
        id_vars=["station_id", "station_type", "wfd_c2_mgt_catchment_name"],
        value_vars=ratio_cols,
        var_name="ratio",
        value_name="value",
    )
    ratio_long = ratio_long.replace([np.inf, -np.inf], np.nan).dropna(subset=["value"])
    ratio_long = ratio_long[ratio_long["value"] > 0]

    plt.figure(figsize=(11, 6))
    sns.boxplot(data=ratio_long, x="ratio", y="value", showfliers=False, color="#66AA77")
    plt.yscale("log")
    plt.xlabel("")
    plt.ylabel("Ratio value, log scale")
    plt.title("Mine-related stations: metal ratio distributions")
    plt.tight_layout()
    plt.savefig(FIGURES / "mine_related_ratio_distributions.png", dpi=220)
    plt.close()

    top_types = data["station_type"].value_counts(dropna=True).head(6).index
    typed = ratio_long[ratio_long["station_type"].isin(top_types)]
    plt.figure(figsize=(14, 7))
    sns.boxplot(
        data=typed,
        x="ratio",
        y="value",
        hue="station_type",
        showfliers=False,
    )
    plt.yscale("log")
    plt.xlabel("")
    plt.ylabel("Ratio value, log scale")
    plt.title("Mine-related stations: ratios by station type")
    plt.legend(title="Station type", fontsize=8, title_fontsize=9)
    plt.tight_layout()
    plt.savefig(FIGURES / "mine_related_ratios_by_station_type.png", dpi=220)
    plt.close()


def main() -> None:
    FIGURES.mkdir(exist_ok=True)
    mine = load_mine_data()
    mine_with_ratios = add_ratios(mine)

    coverage = parameter_coverage(mine)
    coverage.to_csv(PROCESSED / "mine_related_parameter_coverage.csv", index=False)

    correlations = correlation_table(mine)
    correlations.to_csv(PROCESSED / "mine_related_correlations.csv", index=False)

    ratio_cols = list(RATIO_SPECS)
    mine_with_ratios.to_csv(PROCESSED / "mine_related_stations_with_ratios.csv", index=False)
    ratio_summary(mine_with_ratios).to_csv(PROCESSED / "mine_related_ratio_summary.csv", index=False)
    ratio_summary(mine_with_ratios, "station_type").to_csv(
        PROCESSED / "mine_related_ratio_summary_by_station_type.csv", index=False
    )
    ratio_summary(mine_with_ratios, "wfd_c2_mgt_catchment_name").to_csv(
        PROCESSED / "mine_related_ratio_summary_by_catchment.csv", index=False
    )

    plot_correlation_heatmap(mine)
    plot_scatterplots(mine)
    plot_ratio_boxplots(mine_with_ratios)

    print(f"Mine-related rows: {len(mine):,}")
    print(f"Mine-related stations: {mine['station_id'].nunique():,}")
    print(f"Ratio columns: {', '.join(ratio_cols)}")
    print(f"Wrote outputs to: {PROCESSED}")
    print(f"Wrote figures to: {FIGURES}")


if __name__ == "__main__":
    main()
