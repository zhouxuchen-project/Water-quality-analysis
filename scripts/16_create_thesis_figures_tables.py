from __future__ import annotations

import json
import shutil
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"
SENSITIVITY = ROOT / "results" / "7.5_sensitivity"
RESULTS = ROOT / "results" / "thesis"


def setup_style() -> None:
    sns.set_theme(style="whitegrid", context="paper")
    plt.rcParams.update(
        {
            "font.family": "Arial",
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.labelsize": 10,
            "legend.fontsize": 8.5,
            "figure.dpi": 120,
            "savefig.bbox": "tight",
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )


def export_excel(path: Path, sheets: dict[str, pd.DataFrame]) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, index=False, sheet_name=name[:31])
            worksheet = writer.book[name[:31]]
            worksheet.freeze_panes = "A2"
            for column in worksheet.columns:
                values = [str(cell.value) if cell.value is not None else "" for cell in column[:250]]
                width = min(max(max(map(len, values), default=0) + 2, 11), 48)
                worksheet.column_dimensions[column[0].column_letter].width = width


def make_coverage_table() -> pd.DataFrame:
    coverage = pd.read_csv(PROCESSED / "all_vs_mine_parameter_coverage.csv")
    audit = pd.read_csv(PROCESSED / "raw_quality_flag_audit.csv")
    coverage = coverage.merge(
        audit[["parameter", "deviating_percent", "less_than_percent"]],
        on="parameter",
        how="left",
    )
    coverage["unit"] = coverage["parameter"].map(
        {
            "lead": "ug/L",
            "zinc": "ug/L",
            "copper": "ug/L",
            "calcium": "mg/L",
            "ph": "pH units",
            "hardness": "mg/L",
        }
    )
    columns = [
        "dataset",
        "parameter",
        "unit",
        "n_records",
        "n_stations",
        "first_date",
        "last_date",
        "median",
        "minimum",
        "maximum",
        "deviating_percent",
        "less_than_percent",
    ]
    return coverage[columns]


def stable_candidate_ids() -> set[str]:
    flow = pd.read_csv(SENSITIVITY / "7.5_Flow_Window_Stations.csv")
    method_sets = {
        method: set(
            group.loc[group["systematic_candidate"], "station_id"].astype(str)
        )
        for method, group in flow.groupby("method")
    }
    manual = pd.read_csv(SENSITIVITY / "7.5_Uncensored_Manual_Validation.csv")
    manual_ids = set(
        manual.loc[manual["manual_systematic_candidate_uncensored"], "station_id"].astype(str)
    )
    stable = manual_ids.copy()
    for ids in method_sets.values():
        stable &= ids
    return stable


def make_robust_candidates() -> pd.DataFrame:
    stable = stable_candidate_ids()
    flow = pd.read_csv(SENSITIVITY / "7.5_Flow_Window_Stations.csv")
    same = flow[
        flow["method"].eq("same_day") & flow["station_id"].astype(str).isin(stable)
    ].copy()
    same = same.rename(
        columns={
            "n_with_flow": "automatic_n_with_flow",
            "n_low_flow_high_pbzn": "automatic_n_low_flow_high_pbzn",
            "n_low_flow_high_pb_low_zn": "automatic_n_low_flow_high_pb_low_zn",
            "pct_low_flow_high_pbzn": "automatic_pct_low_flow_high_pbzn",
        }
    )
    manual = pd.read_csv(SENSITIVITY / "7.5_Uncensored_Manual_Validation.csv")
    matches = pd.read_csv(PROCESSED / "pbzn_nearest_flow_station_matches.csv")
    samples = pd.read_csv(SENSITIVITY / "7.5_Uncensored_PbZn_Flow_Samples.csv")
    sample_summary = (
        samples[samples["station_id"].astype(str).isin(stable)]
        .groupby("station_id")
        .agg(
            uncensored_pbzn_samples=("pb_zn_ratio", "size"),
            median_lead_ug_l=("lead_value", "median"),
            median_zinc_ug_l=("zinc_value", "median"),
            median_pb_zn_ratio=("pb_zn_ratio", "median"),
            maximum_pb_zn_ratio=("pb_zn_ratio", "max"),
        )
        .reset_index()
    )
    manual_columns = [
        "station_id",
        "manual_nrfa_id",
        "manual_nrfa_name",
        "manual_decision",
        "manual_n_with_flow",
        "manual_n_low_flow_high_pbzn",
        "manual_n_low_flow_high_pb_low_zn",
        "manual_pct_low_flow_high_pbzn",
        "status",
    ]
    match_columns = [
        "station_id",
        "station_type",
        "wfd_c2_mgt_catchment_name",
        "easting",
        "northing",
        "nrfa_station_id",
        "nrfa_station_name",
        "nrfa_river",
        "flow_match_distance_km",
    ]
    result = (
        same.merge(manual[manual_columns], on="station_id", how="left")
        .merge(matches[match_columns], on="station_id", how="left")
        .merge(sample_summary, on="station_id", how="left")
    )
    result["stable_across_all_checks"] = True
    return result.sort_values(
        ["manual_n_low_flow_high_pbzn", "automatic_n_low_flow_high_pbzn"],
        ascending=False,
    )


def plot_study_area(robust: pd.DataFrame) -> None:
    stations = pd.read_csv(RAW / "stations" / "nrw_water_quality_archive_stations.csv")
    mine_ids = set(
        pd.read_csv(PROCESSED / "mine_related_stations_summary.csv")["station_id"].astype(str)
    )
    stations["station_number"] = stations["station_number"].astype(str)
    all_xy = stations.dropna(subset=["easting", "northing"])
    mine_xy = all_xy[all_xy["station_number"].isin(mine_ids)]

    metadata = pd.read_csv(RAW / "river_flow" / "nrfa_station_metadata_all.csv")
    manual_ids = robust["manual_nrfa_id"].dropna().astype(int).unique()
    gauges = metadata[metadata["nrfa_station_id"].isin(manual_ids)].dropna(
        subset=["easting", "northing"]
    )

    fig, ax = plt.subplots(figsize=(7.2, 8.2))
    ax.scatter(
        all_xy["easting"],
        all_xy["northing"],
        s=4,
        color="#D4D7D9",
        alpha=0.45,
        linewidth=0,
        label="All NRW water-quality stations",
    )
    ax.scatter(
        mine_xy["easting"],
        mine_xy["northing"],
        s=12,
        color="#4D7895",
        alpha=0.65,
        linewidth=0,
        label="Mine-related stations",
    )
    ax.scatter(
        robust["easting"],
        robust["northing"],
        s=52,
        color="#B6463C",
        edgecolor="white",
        linewidth=0.7,
        zorder=4,
        label="Nine robust candidate stations",
    )
    ax.scatter(
        gauges["easting"],
        gauges["northing"],
        s=62,
        marker="^",
        color="#222222",
        edgecolor="white",
        linewidth=0.7,
        zorder=5,
        label="Manually selected NRFA gauges",
    )
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("British National Grid easting (m)")
    ax.set_ylabel("British National Grid northing (m)")
    ax.set_title("Water-quality stations and robust Pb/Zn-flow candidates in Wales")
    ax.legend(loc="lower left", frameon=True, facecolor="white")
    fig.savefig(RESULTS / "Figure_3_1_Study_Area.png", dpi=300)
    plt.close(fig)


def plot_workflow() -> None:
    fig, ax = plt.subplots(figsize=(12, 3.6))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 4)
    ax.axis("off")
    boxes = [
        (0.25, "1. NRW archive", "2000-2026 annual files\nSix target parameters"),
        (3.25, "2. Quality control", "Units and water media\nDeviating and censored flags"),
        (6.25, "3. Pb/Zn-flow linkage", "Mine-related stations\nNRFA daily mean discharge"),
        (9.25, "4. Validation", "Censoring and time windows\nManual gauge matching"),
    ]
    colours = ["#DCE8EF", "#E8E5D5", "#DCE9DF", "#F0DDD8"]
    for (x, title, body), colour in zip(boxes, colours, strict=False):
        rectangle = plt.Rectangle(
            (x, 1.0),
            2.5,
            2.0,
            facecolor=colour,
            edgecolor="#5A6063",
            linewidth=1.0,
        )
        ax.add_patch(rectangle)
        ax.text(x + 1.25, 2.45, title, ha="center", va="center", fontsize=11, weight="bold")
        ax.text(x + 1.25, 1.65, body, ha="center", va="center", fontsize=9.5, linespacing=1.35)
    for x in [2.78, 5.78, 8.78]:
        ax.annotate(
            "",
            xy=(x + 0.40, 2.0),
            xytext=(x, 2.0),
            arrowprops=dict(arrowstyle="-|>", color="#444444", lw=1.5),
        )
    ax.text(
        6,
        0.35,
        "Output: hydrologically validated, censoring-aware candidate systems for remediation monitoring",
        ha="center",
        va="center",
        fontsize=10.5,
        weight="bold",
        color="#263238",
    )
    fig.savefig(RESULTS / "Figure_3_2_Analytical_Workflow.png", dpi=300)
    plt.close(fig)


def plot_pbzn_scatter(samples: pd.DataFrame) -> None:
    data = samples[(samples["lead_value"] > 0) & (samples["zinc_value"] > 0)].copy()
    data["highlight"] = np.where(
        data["low_flow_high_ratio"].fillna(False),
        "Low flow and high Pb/Zn",
        "Other uncensored pair",
    )
    fig, ax = plt.subplots(figsize=(7.4, 6.2))
    palette = {
        "Other uncensored pair": "#5C82A0",
        "Low flow and high Pb/Zn": "#C3483E",
    }
    sns.scatterplot(
        data=data,
        x="zinc_value",
        y="lead_value",
        hue="highlight",
        hue_order=["Other uncensored pair", "Low flow and high Pb/Zn"],
        palette=palette,
        s=18,
        alpha=0.48,
        linewidth=0,
        ax=ax,
    )
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.axhline(510.0, color="#333333", linestyle="--", linewidth=1)
    ax.axvline(452.0, color="#333333", linestyle=":", linewidth=1)
    ax.set_xlabel("Zinc (ug/L, log scale)")
    ax.set_ylabel("Lead (ug/L, log scale)")
    ax.set_title("Uncensored Pb and Zn pairs at mine-related stations")
    ax.text(
        0.03,
        0.97,
        "Spearman rho = 0.437; n = 7,061",
        transform=ax.transAxes,
        va="top",
        bbox=dict(facecolor="white", edgecolor="#BBBBBB", alpha=0.9),
    )
    ax.legend(title="", loc="lower right", frameon=True)
    fig.savefig(RESULTS / "Figure_4_1_PbZn_Scatter.png", dpi=300)
    plt.close(fig)


def plot_ratio_by_flow(samples: pd.DataFrame) -> pd.DataFrame:
    data = samples[samples["flow_percentile"].notna()].copy()
    data["flow_class"] = pd.cut(
        data["flow_percentile"],
        bins=[-np.inf, 0.10, 0.25, np.inf],
        labels=["Very low (<=10th)", "Low (10th-25th)", "Normal/high (>25th)"],
        right=True,
    )
    order = ["Very low (<=10th)", "Low (10th-25th)", "Normal/high (>25th)"]
    summary = (
        data.groupby("flow_class", observed=False)["pb_zn_ratio"]
        .agg(n="size", median="median", q25=lambda x: x.quantile(0.25), q75=lambda x: x.quantile(0.75))
        .reset_index()
    )
    fig, ax = plt.subplots(figsize=(7.4, 5.8))
    sns.boxplot(
        data=data,
        x="flow_class",
        y="pb_zn_ratio",
        order=order,
        showfliers=False,
        palette=["#B6463C", "#D39B43", "#4D7895"],
        hue="flow_class",
        legend=False,
        ax=ax,
    )
    ax.set_yscale("log")
    ax.set_xlabel("Sampling-day flow class")
    ax.set_ylabel("Pb/Zn ratio (log scale)")
    ax.set_title("Pb/Zn ratio by station-specific flow percentile")
    fig.savefig(RESULTS / "Figure_4_2_Ratio_By_Flow_Class.png", dpi=300)
    plt.close(fig)
    return summary


def plot_candidates(robust: pd.DataFrame) -> None:
    data = robust.sort_values("manual_n_low_flow_high_pbzn", ascending=True).copy()
    labels = data["station_name"].str.slice(0, 46)
    y = np.arange(len(data))
    height = 0.36
    fig, ax = plt.subplots(figsize=(9.4, 6.4))
    ax.barh(
        y - height / 2,
        data["automatic_n_low_flow_high_pbzn"],
        height,
        color="#4D7895",
        label="Automatic nearest gauge",
    )
    ax.barh(
        y + height / 2,
        data["manual_n_low_flow_high_pbzn"],
        height,
        color="#C46A45",
        label="Manual hydrological gauge",
    )
    ax.set_yticks(y, labels)
    ax.set_xlabel("Low-flow samples with high Pb/Zn")
    ax.set_ylabel("")
    ax.set_title("Nine candidate stations stable across all sensitivity checks")
    ax.legend(loc="lower right")
    ax.xaxis.set_major_locator(plt.MaxNLocator(integer=True))
    fig.savefig(RESULTS / "Figure_4_3_Robust_Candidates.png", dpi=300)
    plt.close(fig)


def plot_matching_agreement() -> None:
    data = pd.read_csv(PROCESSED / "manual_matching_agreement_by_distance.csv")
    labels = ["<2 km", "2-<7 km", ">=7 km"]
    fig, ax = plt.subplots(figsize=(6.8, 5.2))
    bars = ax.bar(labels, data["agreement_rate"] * 100, color=["#3F7D65", "#D39B43", "#B6463C"])
    for bar, (_, row) in zip(bars, data.iterrows(), strict=False):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 3,
            f"{int(row['n_exact_agreement'])}/{int(row['n_sites'])}",
            ha="center",
            va="bottom",
            weight="bold",
        )
    ax.set_ylim(0, 112)
    ax.set_xlabel("Automatic match distance")
    ax.set_ylabel("Exact automatic/manual agreement (%)")
    ax.set_title("Gauge-matching agreement declines with distance")
    fig.savefig(RESULTS / "Figure_4_4_Matching_Agreement.png", dpi=300)
    plt.close(fig)


def plot_sensitivity() -> None:
    censoring = pd.read_csv(SENSITIVITY / "7.5_Censoring_Metrics.csv")
    windows = pd.read_csv(SENSITIVITY / "7.5_Flow_Window_Metrics.csv")
    censoring_labels = {
        "as_reported": "RL as value",
        "half_reporting_limit": "Half RL",
        "uncensored_only": "Uncensored",
    }
    window_labels = {
        "same_day": "Same day",
        "antecedent_3_day_mean": "3-day mean",
        "antecedent_7_day_mean": "7-day mean",
    }
    censoring["label"] = censoring["scenario"].map(censoring_labels)
    windows["label"] = windows["method"].map(window_labels)
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.8), constrained_layout=True)
    sns.barplot(data=censoring, x="label", y="n_candidates", color="#4D7895", ax=axes[0])
    axes[0].set_title("Treatment of censored concentrations")
    axes[0].set_xlabel("")
    axes[0].set_ylabel("Candidate stations")
    sns.barplot(data=windows, x="label", y="n_candidates", color="#C46A45", ax=axes[1])
    axes[1].set_title("Flow time window, uncensored pairs")
    axes[1].set_xlabel("")
    axes[1].set_ylabel("Candidate stations")
    for ax in axes:
        ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    fig.savefig(RESULTS / "Figure_4_5_Sensitivity.png", dpi=300)
    plt.close(fig)


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    setup_style()

    coverage = make_coverage_table()
    censoring = pd.read_csv(SENSITIVITY / "7.5_Censoring_Metrics.csv")
    flow_windows = pd.read_csv(SENSITIVITY / "7.5_Flow_Window_Metrics.csv")
    matching = pd.read_csv(PROCESSED / "manual_matching_validation_metrics.csv")
    robust = make_robust_candidates()
    samples = pd.read_csv(SENSITIVITY / "7.5_Uncensored_PbZn_Flow_Samples.csv", low_memory=False)
    flow_class = plot_ratio_by_flow(samples)

    coverage.to_csv(RESULTS / "Table_3_1_Data_Coverage.csv", index=False)
    censoring.to_csv(RESULTS / "Table_4_1_Censoring_Sensitivity.csv", index=False)
    flow_windows.to_csv(RESULTS / "Table_4_2_Flow_Window_Sensitivity.csv", index=False)
    matching.to_csv(RESULTS / "Table_4_3_Manual_Matching_Validation.csv", index=False)
    robust.to_csv(RESULTS / "Table_4_4_Robust_Candidate_Stations.csv", index=False)
    flow_class.to_csv(RESULTS / "Table_4_5_Ratio_By_Flow_Class.csv", index=False)
    export_excel(
        RESULTS / "Thesis_Tables.xlsx",
        {
            "data_coverage": coverage,
            "censoring": censoring,
            "flow_windows": flow_windows,
            "manual_matching": matching,
            "robust_candidates": robust,
            "flow_classes": flow_class,
        },
    )

    plot_study_area(robust)
    plot_workflow()
    plot_pbzn_scatter(samples)
    plot_candidates(robust)
    plot_matching_agreement()
    plot_sensitivity()

    shutil.copy2(
        ROOT / "results" / "7.2_mine_related" / "7.2_Correlation_Heatmap.png",
        RESULTS / "Figure_A_1_Exploratory_Correlation_Heatmap.png",
    )

    key_numbers = {
        "mine_related_stations": 595,
        "mine_related_station_dates": 20178,
        "uncensored_pbzn_samples": int(len(samples)),
        "uncensored_pbzn_stations": int(samples["station_id"].nunique()),
        "uncensored_same_day_flow_samples": int(samples["has_flow"].sum()),
        "uncensored_pbzn_spearman": float(
            samples[["lead_value", "zinc_value"]].corr(method="spearman").iloc[0, 1]
        ),
        "uncensored_ratio_flow_spearman": float(
            samples.loc[samples["has_flow"], ["pb_zn_ratio", "flow_percentile"]]
            .corr(method="spearman")
            .iloc[0, 1]
        ),
        "uncensored_low_flow_high_ratio_events": int(
            samples["low_flow_high_ratio"].sum()
        ),
        "uncensored_low_flow_high_pb_low_zn_events": int(
            samples["low_flow_high_pb_low_zn"].sum()
        ),
        "uncensored_automatic_candidates": int(
            censoring.loc[
                censoring["scenario"].eq("uncensored_only"), "n_candidates"
            ].iloc[0]
        ),
        "robust_candidates_all_checks": int(len(robust)),
        "automatic_manual_match_agreement_rate": float(
            matching.loc[
                matching["metric"].eq("Exact station agreement rate"), "value"
            ].iloc[0]
        ),
    }
    (RESULTS / "thesis_key_numbers.json").write_text(
        json.dumps(key_numbers, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(key_numbers, indent=2))
    print(f"Wrote thesis tables and figures to {RESULTS}")


if __name__ == "__main__":
    main()
