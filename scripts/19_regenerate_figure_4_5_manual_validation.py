"""Regenerate the thesis manual flow-matching validation figure.

The analytical values are read from the existing processed data products. The
only numerical transformation is converting flow percentiles from fractions to
percentage points for display.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import spearmanr


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
OUT = ROOT / "results" / "final_figures"
OUT.mkdir(parents=True, exist_ok=True)

OUTPUT_STEM = OUT / "Figure_4_5_Manual_Flow_Matching_Validation_Clean"

COLORS = {
    "green": "#2F7F68",
    "gold": "#D5A33B",
    "blue": "#3F7898",
    "red": "#BC4B47",
    "gray": "#AAB4BA",
    "dark": "#243238",
    "axis": "#748188",
    "grid": "#DCE3E6",
}


def load_and_validate() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    distance = pd.read_csv(DATA / "manual_matching_agreement_by_distance.csv")
    samples = pd.read_csv(DATA / "pbzn_manual_flow_validation_samples.csv", low_memory=False)
    metrics = pd.read_csv(DATA / "manual_matching_validation_metrics.csv")

    paired = samples[samples["both_methods_have_flow"].fillna(False)].copy()
    paired = paired.dropna(subset=["flow_percentile", "manual_flow_percentile"])
    changed = paired["low_flow_status_changed"].fillna(False).astype(bool)

    for column in ("flow_percentile", "manual_flow_percentile"):
        values = paired[column].to_numpy(dtype=float)
        if not np.isfinite(values).all() or values.min() < 0 or values.max() > 1:
            raise ValueError(f"{column} must contain finite fractions from 0 to 1")

    expected_distance = [(6, 6), (15, 5), (9, 0)]
    observed_distance = list(
        zip(distance["n_sites"].astype(int), distance["n_exact_agreement"].astype(int))
    )
    if observed_distance != expected_distance:
        raise ValueError(f"Unexpected distance summary: {observed_distance}")

    metric_map = dict(zip(metrics["metric"], metrics["value"].astype(float)))
    outcomes = pd.DataFrame(
        {
            "Outcome": ["Retained", "Disqualified", "Not evaluable"],
            "Sites": [
                int(metric_map["Original candidate sites retained after manual matching"]),
                int(metric_map["Original candidate sites lost after manual matching"]),
                int(metric_map["Original candidate sites not evaluable after manual matching"]),
            ],
        }
    )

    rho, p_value = spearmanr(
        paired["flow_percentile"], paired["manual_flow_percentile"], nan_policy="omit"
    )
    qa = {
        "source_sample_rows": int(len(samples)),
        "paired_rows_plotted": int(len(paired)),
        "unchanged_rows": int((~changed).sum()),
        "changed_rows": int(changed.sum()),
        "changed_percentage": float(changed.mean() * 100),
        "spearman_rho": float(rho),
        "spearman_p_value": float(p_value),
        "display_transform": "flow percentile fractions multiplied by 100",
        "excluded_rows": int(len(samples) - len(paired)),
        "exclusion_rule": "rows without flow percentiles under both matching methods",
        "distance_groups": distance.to_dict(orient="records"),
        "candidate_outcomes": outcomes.to_dict(orient="records"),
    }

    if len(paired) != 1335 or int(changed.sum()) != 120:
        raise ValueError("Paired-sample totals do not match the validated thesis results")
    if not np.isclose(rho, 0.8735296508237783, atol=1e-12):
        raise ValueError(f"Unexpected Spearman rho: {rho}")
    if outcomes["Sites"].tolist() != [17, 3, 1]:
        raise ValueError(f"Unexpected candidate outcomes: {outcomes['Sites'].tolist()}")

    return distance, paired, outcomes, qa


def style_axis(ax: plt.Axes, grid_axis: str) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(COLORS["axis"])
        ax.spines[side].set_linewidth(0.8)
    ax.tick_params(axis="both", colors="black", width=0.75, length=3)
    ax.grid(axis=grid_axis, color=COLORS["grid"], linewidth=0.75, zorder=0)
    ax.set_axisbelow(True)


def panel_label(ax: plt.Axes, label: str, x: float = -0.16) -> None:
    ax.text(
        x,
        1.04,
        label,
        transform=ax.transAxes,
        fontsize=11,
        fontweight="bold",
        ha="left",
        va="bottom",
        color=COLORS["dark"],
    )


def build_figure(
    distance: pd.DataFrame, paired: pd.DataFrame, outcomes: pd.DataFrame
) -> plt.Figure:
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
            "font.size": 8.0,
            "axes.titlesize": 9.5,
            "axes.titleweight": "normal",
            "axes.labelsize": 8.5,
            "xtick.labelsize": 7.5,
            "ytick.labelsize": 7.5,
            "legend.fontsize": 6.8,
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
        }
    )

    fig = plt.figure(figsize=(7.2, 3.65), facecolor="white")
    grid = fig.add_gridspec(1, 3, width_ratios=[0.88, 1.38, 0.96], wspace=0.47)
    ax_distance = fig.add_subplot(grid[0, 0])
    ax_scatter = fig.add_subplot(grid[0, 1])
    ax_outcome = fig.add_subplot(grid[0, 2])

    # a | Distance-stratified agreement
    x = np.arange(len(distance))
    agreement = distance["agreement_rate"].to_numpy(dtype=float) * 100
    bars = ax_distance.bar(
        x,
        agreement,
        width=0.72,
        color=[COLORS["green"], COLORS["gold"], COLORS["red"]],
        edgecolor="white",
        linewidth=0.7,
        zorder=2,
    )
    for bar, row in zip(bars, distance.itertuples()):
        label_y = max(float(row.agreement_rate) * 100 + 3.2, 4.0)
        ax_distance.text(
            bar.get_x() + bar.get_width() / 2,
            label_y,
            f"{int(row.n_exact_agreement)}/{int(row.n_sites)}",
            ha="center",
            va="bottom",
            fontsize=7.4,
            fontweight="bold",
        )
    ax_distance.set_xticks(x, ["<2 km", "2–<7 km", "≥7 km"])
    ax_distance.set_yticks([0, 25, 50, 75, 100])
    ax_distance.set_ylim(0, 110)
    ax_distance.set_ylabel("Exact gauge agreement (%)")
    ax_distance.set_title("Agreement by distance", pad=8)
    style_axis(ax_distance, "y")
    panel_label(ax_distance, "a", -0.18)

    # b | Automatic versus manually validated flow percentiles
    changed = paired["low_flow_status_changed"].fillna(False).astype(bool)
    automatic = paired["flow_percentile"].to_numpy(dtype=float) * 100
    manual = paired["manual_flow_percentile"].to_numpy(dtype=float) * 100
    ax_scatter.scatter(
        automatic[~changed],
        manual[~changed],
        s=10,
        color=COLORS["blue"],
        alpha=0.25,
        edgecolors="none",
        rasterized=True,
        zorder=2,
    )
    ax_scatter.scatter(
        automatic[changed],
        manual[changed],
        s=13,
        color=COLORS["red"],
        alpha=0.68,
        edgecolors="none",
        rasterized=True,
        zorder=3,
    )
    ax_scatter.plot(
        [0, 100], [0, 100], color=COLORS["dark"], linestyle="--", linewidth=1.0, zorder=4
    )
    ax_scatter.axvline(25, color=COLORS["axis"], linestyle=":", linewidth=0.9, zorder=1)
    ax_scatter.axhline(25, color=COLORS["axis"], linestyle=":", linewidth=0.9, zorder=1)
    ax_scatter.set_xlim(0, 100)
    ax_scatter.set_ylim(0, 100)
    ax_scatter.set_xticks([0, 25, 50, 75, 100])
    ax_scatter.set_yticks([0, 25, 50, 75, 100])
    ax_scatter.set_xlabel("Automatic flow percentile (%)")
    ax_scatter.set_ylabel("Manually validated flow percentile (%)")
    ax_scatter.set_title("Flow-percentile agreement", pad=8)
    style_axis(ax_scatter, "both")
    panel_label(ax_scatter, "b", -0.16)

    # c | Candidate status after manual validation
    y = np.array([2, 1, 0])
    values = outcomes["Sites"].to_numpy(dtype=int)
    outcome_bars = ax_outcome.barh(
        y,
        values,
        height=0.58,
        color=[COLORS["green"], COLORS["red"], COLORS["gray"]],
        edgecolor="white",
        linewidth=0.7,
        zorder=2,
    )
    for bar, value in zip(outcome_bars, values):
        ax_outcome.text(
            value + 0.35,
            bar.get_y() + bar.get_height() / 2,
            str(value),
            va="center",
            ha="left",
            fontsize=7.5,
            fontweight="bold",
        )
    ax_outcome.set_yticks(y, outcomes["Outcome"])
    ax_outcome.set_xticks([0, 5, 10, 15])
    ax_outcome.set_xlim(0, 19)
    ax_outcome.set_xlabel("Initial candidate stations")
    ax_outcome.set_title("Candidate status", pad=8)
    style_axis(ax_outcome, "x")
    panel_label(ax_outcome, "c", -0.20)

    fig.subplots_adjust(left=0.075, right=0.985, top=0.86, bottom=0.20)
    return fig


def save_outputs(fig: plt.Figure, qa: dict) -> None:
    fig.savefig(OUTPUT_STEM.with_suffix(".png"), dpi=600, facecolor="white")
    fig.savefig(OUTPUT_STEM.with_suffix(".tiff"), dpi=600, facecolor="white")
    fig.savefig(OUTPUT_STEM.with_suffix(".pdf"), facecolor="white")
    fig.savefig(OUTPUT_STEM.with_suffix(".svg"), facecolor="white")
    with OUTPUT_STEM.with_name(OUTPUT_STEM.name + "_QA.json").open(
        "w", encoding="utf-8"
    ) as handle:
        json.dump(qa, handle, indent=2, ensure_ascii=False)


def main() -> None:
    distance, paired, outcomes, qa = load_and_validate()
    figure = build_figure(distance, paired, outcomes)
    save_outputs(figure, qa)
    plt.close(figure)
    print(json.dumps(qa, indent=2))
    print(f"Saved figure outputs to {OUTPUT_STEM}")


if __name__ == "__main__":
    main()
