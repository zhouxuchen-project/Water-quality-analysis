from __future__ import annotations

import itertools

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats

from project_config import FIGURES_DIR, PROCESSED_DIR, TARGET_PARAMETERS, ensure_directories


LONG_PATH = PROCESSED_DIR / "water_quality_selected_long.csv"
WIDE_PATH = PROCESSED_DIR / "water_quality_selected_wide.csv"


def safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denominator = denominator.replace(0, np.nan)
    return numerator / denominator


def correlation_rows(wide: pd.DataFrame) -> pd.DataFrame:
    parameters = [param for param in TARGET_PARAMETERS if param in wide.columns]
    rows = []
    for left, right in itertools.combinations(parameters, 2):
        pair = wide[[left, right]].dropna()
        if len(pair) < 5:
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


def add_ratio_columns(wide: pd.DataFrame) -> pd.DataFrame:
    wide = wide.copy()
    ratio_specs = [
        ("zinc_to_lead", "zinc", "lead"),
        ("copper_to_zinc", "copper", "zinc"),
        ("lead_to_calcium", "lead", "calcium"),
        ("zinc_to_calcium", "zinc", "calcium"),
        ("copper_to_calcium", "copper", "calcium"),
        ("lead_to_hardness", "lead", "hardness"),
        ("zinc_to_hardness", "zinc", "hardness"),
        ("copper_to_hardness", "copper", "hardness"),
    ]
    for ratio_name, numerator, denominator in ratio_specs:
        if numerator in wide.columns and denominator in wide.columns:
            wide[ratio_name] = safe_ratio(wide[numerator], wide[denominator])
    return wide


def main() -> None:
    ensure_directories()
    if not LONG_PATH.exists() or not WIDE_PATH.exists():
        print("Cleaned water quality files are missing.")
        print("Run scripts/03_clean_water_quality.py after adding raw NRW water quality files.")
        return

    long = pd.read_csv(LONG_PATH, parse_dates=["sample_date"], low_memory=False)
    wide = pd.read_csv(WIDE_PATH, parse_dates=["sample_date"])
    value_col = "value_standardised" if "value_standardised" in long.columns else "value"

    summary = (
        long.groupby(["canonical_parameter", "standard_unit"], dropna=False)
        .agg(
            n_records=(value_col, "size"),
            n_stations=("station_id", "nunique"),
            first_date=("sample_date", "min"),
            last_date=("sample_date", "max"),
            mean=(value_col, "mean"),
            median=(value_col, "median"),
            q25=(value_col, lambda x: x.quantile(0.25)),
            q75=(value_col, lambda x: x.quantile(0.75)),
            minimum=(value_col, "min"),
            maximum=(value_col, "max"),
        )
        .reset_index()
        .sort_values("n_records", ascending=False)
    )
    summary.to_csv(PROCESSED_DIR / "parameter_summary_statistics.csv", index=False)

    station_coverage = (
        long.groupby(["station_id", "station_name", "canonical_parameter"], dropna=False)
        .size()
        .unstack("canonical_parameter", fill_value=0)
        .reset_index()
    )
    station_coverage["n_target_parameters_present"] = (
        station_coverage[[col for col in TARGET_PARAMETERS if col in station_coverage.columns]] > 0
    ).sum(axis=1)
    station_coverage.sort_values(
        ["n_target_parameters_present", "station_id"], ascending=[False, True]
    ).to_csv(PROCESSED_DIR / "station_parameter_coverage.csv", index=False)

    correlations = correlation_rows(wide)
    correlations.to_csv(PROCESSED_DIR / "parameter_correlations.csv", index=False)

    wide_with_ratios = add_ratio_columns(wide)
    ratio_columns = [col for col in wide_with_ratios.columns if "_to_" in col]
    if ratio_columns:
        wide_with_ratios[
            ["station_id", "station_name", "sample_date", *ratio_columns]
        ].to_csv(PROCESSED_DIR / "metal_ratio_samples.csv", index=False)

    sns.set_theme(style="whitegrid")

    plt.figure(figsize=(10, 6))
    plot_data = long.copy()
    plot_data["value_for_plot"] = np.where(plot_data[value_col] > 0, plot_data[value_col], np.nan)
    sns.boxplot(
        data=plot_data,
        x="canonical_parameter",
        y="value_for_plot",
        color="#66AA77",
        showfliers=False,
    )
    plt.yscale("log")
    plt.xlabel("")
    plt.ylabel("Value, log scale")
    plt.title("Distribution of selected water quality parameters")
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "selected_parameter_distributions.png", dpi=220)
    plt.close()

    parameters = [param for param in TARGET_PARAMETERS if param in wide.columns]
    if len(parameters) >= 2:
        corr = wide[parameters].corr(method="spearman", min_periods=5)
        corr = corr.dropna(axis=0, how="all").dropna(axis=1, how="all")
        plt.figure(figsize=(8, 7))
        sns.heatmap(corr, annot=True, cmap="vlag", center=0, vmin=-1, vmax=1, square=True)
        plt.title("Spearman correlation among selected parameters")
        plt.tight_layout()
        plt.savefig(FIGURES_DIR / "spearman_correlation_heatmap.png", dpi=220)
        plt.close()

    scatter_pairs = [("lead", "zinc"), ("zinc", "copper"), ("calcium", "zinc"), ("ph", "zinc")]
    available_pairs = [(x, y) for x, y in scatter_pairs if x in wide.columns and y in wide.columns]
    if available_pairs:
        fig, axes = plt.subplots(1, len(available_pairs), figsize=(5 * len(available_pairs), 4))
        if len(available_pairs) == 1:
            axes = [axes]
        for ax, (x_col, y_col) in zip(axes, available_pairs, strict=False):
            pair = wide[[x_col, y_col]].dropna()
            if x_col != "ph":
                pair = pair[pair[x_col] > 0]
            if y_col != "ph":
                pair = pair[pair[y_col] > 0]
            sns.scatterplot(data=pair, x=x_col, y=y_col, s=18, alpha=0.55, ax=ax)
            if x_col != "ph":
                ax.set_xscale("log")
            if y_col != "ph":
                ax.set_yscale("log")
            ax.set_title(f"{TARGET_PARAMETERS[x_col]['label']} vs {TARGET_PARAMETERS[y_col]['label']}")
        plt.tight_layout()
        plt.savefig(FIGURES_DIR / "selected_parameter_scatterplots.png", dpi=220)
        plt.close()

    print(f"Analysed cleaned rows: {len(long):,}")
    print(f"Wrote summaries to: {PROCESSED_DIR}")
    print(f"Wrote figures to: {FIGURES_DIR}")


if __name__ == "__main__":
    main()
