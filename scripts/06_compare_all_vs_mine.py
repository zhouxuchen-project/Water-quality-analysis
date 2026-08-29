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

ALL_WIDE = PROCESSED / "water_quality_selected_wide_with_station_metadata.csv"
MINE_WIDE = PROCESSED / "mine_related_stations_wide.csv"

PARAMETERS = ["lead", "zinc", "copper", "calcium", "ph"]
KEY_PAIRS = [
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
SCATTER_PAIRS = [("lead", "zinc"), ("zinc", "copper"), ("ph", "zinc"), ("ph", "lead")]


def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    all_data = pd.read_csv(ALL_WIDE, parse_dates=["sample_date"], low_memory=False)
    mine_data = pd.read_csv(MINE_WIDE, parse_dates=["sample_date"], low_memory=False)
    return all_data, mine_data


def coverage_rows(data: pd.DataFrame, label: str) -> list[dict[str, object]]:
    rows = []
    for parameter in PARAMETERS + ["hardness"]:
        if parameter not in data.columns:
            continue
        subset = data[data[parameter].notna()]
        rows.append(
            {
                "dataset": label,
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
    return rows


def correlation_for_pair(data: pd.DataFrame, left: str, right: str) -> dict[str, object]:
    pair = data[[left, right]].dropna()
    if left != "ph":
        pair = pair[pair[left] > 0]
    if right != "ph":
        pair = pair[pair[right] > 0]

    if len(pair) < 5:
        return {
            "n_paired_samples": len(pair),
            "pearson_r": np.nan,
            "pearson_p": np.nan,
            "spearman_r": np.nan,
            "spearman_p": np.nan,
        }

    pearson = stats.pearsonr(pair[left], pair[right])
    spearman = stats.spearmanr(pair[left], pair[right])
    return {
        "n_paired_samples": len(pair),
        "pearson_r": pearson.statistic,
        "pearson_p": pearson.pvalue,
        "spearman_r": spearman.statistic,
        "spearman_p": spearman.pvalue,
    }


def comparison_rows(all_data: pd.DataFrame, mine_data: pd.DataFrame) -> list[dict[str, object]]:
    rows = []
    for left, right in KEY_PAIRS:
        all_corr = correlation_for_pair(all_data, left, right)
        mine_corr = correlation_for_pair(mine_data, left, right)
        rows.append(
            {
                "parameter_1": left,
                "parameter_2": right,
                "all_n": all_corr["n_paired_samples"],
                "all_spearman_r": all_corr["spearman_r"],
                "all_pearson_r": all_corr["pearson_r"],
                "mine_n": mine_corr["n_paired_samples"],
                "mine_spearman_r": mine_corr["spearman_r"],
                "mine_pearson_r": mine_corr["pearson_r"],
                "mine_minus_all_spearman": mine_corr["spearman_r"] - all_corr["spearman_r"],
            }
        )
    return rows


def positive_for_log(data: pd.DataFrame, pair: tuple[str, str]) -> pd.DataFrame:
    left, right = pair
    pair_data = data[[left, right]].dropna().copy()
    if left != "ph":
        pair_data = pair_data[pair_data[left] > 0]
    if right != "ph":
        pair_data = pair_data[pair_data[right] > 0]
    return pair_data


def sampled_pair(data: pd.DataFrame, pair: tuple[str, str], n: int = 8000) -> pd.DataFrame:
    pair_data = positive_for_log(data, pair)
    if len(pair_data) > n:
        return pair_data.sample(n=n, random_state=42)
    return pair_data


def plot_heatmaps(all_data: pd.DataFrame, mine_data: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), constrained_layout=True)
    for ax, data, title in [
        (axes[0], all_data, "All Wales stations"),
        (axes[1], mine_data, "Mine-related stations"),
    ]:
        corr = data[PARAMETERS].corr(method="spearman", min_periods=5)
        sns.heatmap(corr, annot=True, cmap="vlag", center=0, vmin=-1, vmax=1, square=True, ax=ax)
        ax.set_title(title)
    fig.suptitle("Spearman correlation comparison")
    fig.savefig(FIGURES / "all_vs_mine_spearman_heatmaps.png", dpi=220)
    plt.close(fig)


def plot_correlation_bars(comparison: pd.DataFrame) -> None:
    plot_data = comparison.copy()
    plot_data["pair"] = plot_data["parameter_1"] + " vs " + plot_data["parameter_2"]
    long = plot_data.melt(
        id_vars=["pair"],
        value_vars=["all_spearman_r", "mine_spearman_r"],
        var_name="dataset",
        value_name="spearman_r",
    )
    long["dataset"] = long["dataset"].map(
        {"all_spearman_r": "All Wales", "mine_spearman_r": "Mine-related"}
    )

    plt.figure(figsize=(11, 6))
    sns.barplot(data=long, x="spearman_r", y="pair", hue="dataset")
    plt.axvline(0, color="black", linewidth=0.8)
    plt.xlabel("Spearman rho")
    plt.ylabel("")
    plt.title("All Wales vs mine-related stations: key parameter relationships")
    plt.tight_layout()
    plt.savefig(FIGURES / "all_vs_mine_key_correlations.png", dpi=220)
    plt.close()


def plot_scatter_comparison(all_data: pd.DataFrame, mine_data: pd.DataFrame) -> None:
    fig, axes = plt.subplots(2, len(SCATTER_PAIRS), figsize=(5 * len(SCATTER_PAIRS), 8))
    for row, (data, label) in enumerate([(all_data, "All Wales"), (mine_data, "Mine-related")]):
        for col, pair in enumerate(SCATTER_PAIRS):
            left, right = pair
            ax = axes[row, col]
            pair_data = sampled_pair(data, pair)
            sns.scatterplot(data=pair_data, x=left, y=right, s=12, alpha=0.45, ax=ax, linewidth=0)
            if left != "ph":
                ax.set_xscale("log")
            if right != "ph":
                ax.set_yscale("log")
            ax.set_title(f"{label}: {left} vs {right}")
    plt.tight_layout()
    plt.savefig(FIGURES / "all_vs_mine_selected_scatterplots.png", dpi=220)
    plt.close(fig)


def main() -> None:
    FIGURES.mkdir(exist_ok=True)
    all_data, mine_data = load_data()

    coverage = pd.DataFrame(
        coverage_rows(all_data, "all_wales") + coverage_rows(mine_data, "mine_related")
    )
    coverage.to_csv(PROCESSED / "all_vs_mine_parameter_coverage.csv", index=False)

    comparison = pd.DataFrame(comparison_rows(all_data, mine_data))
    comparison.to_csv(PROCESSED / "all_vs_mine_correlation_comparison.csv", index=False)

    plot_heatmaps(all_data, mine_data)
    plot_correlation_bars(comparison)
    plot_scatter_comparison(all_data, mine_data)

    print(f"All Wales rows: {len(all_data):,}")
    print(f"Mine-related rows: {len(mine_data):,}")
    print(f"Mine-related stations: {mine_data['station_id'].nunique():,}")
    print(f"Wrote: {PROCESSED / 'all_vs_mine_parameter_coverage.csv'}")
    print(f"Wrote: {PROCESSED / 'all_vs_mine_correlation_comparison.csv'}")
    print(f"Wrote figures to: {FIGURES}")


if __name__ == "__main__":
    main()
