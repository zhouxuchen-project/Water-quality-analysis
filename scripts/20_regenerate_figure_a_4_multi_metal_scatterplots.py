"""Regenerate Appendix Figure A.4 using the complete paired observations.

The figure preserves the original four pairwise comparisons while replacing
parameter names with standard chemical symbols and explicit concentration
units. No observations are sampled or removed for display beyond the stated
pairwise missing-value and positive-concentration requirements.
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
DATA = ROOT / "data" / "processed" / "mine_related_stations_wide.csv"
OUT = ROOT / "results" / "final_figures"
OUT.mkdir(parents=True, exist_ok=True)

OUTPUT_STEM = OUT / "Figure_A_4_Multi_Metal_Scatterplots_Clean"

PAIRS = [
    ("lead", "zinc", "Pb versus Zn", "a"),
    ("zinc", "copper", "Zn versus Cu", "b"),
    ("ph", "zinc", "pH versus Zn", "c"),
    ("ph", "lead", "pH versus Pb", "d"),
]

LABELS = {
    "lead": "Pb (µg/L)",
    "zinc": "Zn (µg/L)",
    "copper": "Cu (µg/L)",
    "ph": "pH",
}

EXPECTED_COUNTS = {
    "lead-zinc": 10_630,
    "zinc-copper": 11_635,
    "ph-zinc": 11_456,
    "ph-lead": 10_546,
}

COLORS = {
    "point": "#3F7898",
    "axis": "#68767D",
    "grid": "#DEE5E8",
    "text": "#1F2A30",
}


def paired_data(data: pd.DataFrame, x_name: str, y_name: str) -> pd.DataFrame:
    """Return finite pairwise observations with positive metal concentrations."""
    pair = data[[x_name, y_name]].replace([np.inf, -np.inf], np.nan).dropna().copy()
    if x_name != "ph":
        pair = pair[pair[x_name] > 0]
    if y_name != "ph":
        pair = pair[pair[y_name] > 0]
    return pair


def load_and_validate() -> tuple[pd.DataFrame, dict]:
    data = pd.read_csv(DATA, low_memory=False)
    qa: dict[str, object] = {
        "source": DATA.name,
        "source_rows": int(len(data)),
        "sampling": "none",
        "pairwise_rule": (
            "complete finite pairs; metal concentrations must be greater than zero"
        ),
        "panels": [],
    }

    for x_name, y_name, title, panel in PAIRS:
        pair = paired_data(data, x_name, y_name)
        key = f"{x_name}-{y_name}"
        expected = EXPECTED_COUNTS[key]
        if len(pair) != expected:
            raise ValueError(
                f"Unexpected paired count for {key}: {len(pair)}; expected {expected}"
            )
        rho, p_value = spearmanr(pair[x_name], pair[y_name], nan_policy="omit")
        qa["panels"].append(
            {
                "panel": panel,
                "title": title,
                "x": x_name,
                "y": y_name,
                "n": int(len(pair)),
                "spearman_rho": float(rho),
                "spearman_p_value": float(p_value),
            }
        )

    return data, qa


def style_axis(ax: plt.Axes) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(COLORS["axis"])
        ax.spines[side].set_linewidth(0.8)
    ax.tick_params(axis="both", colors="black", width=0.75, length=3)
    ax.grid(which="major", color=COLORS["grid"], linewidth=0.65, alpha=0.8)
    ax.set_axisbelow(True)


def panel_label(ax: plt.Axes, label: str) -> None:
    ax.text(
        -0.14,
        1.04,
        label,
        transform=ax.transAxes,
        fontsize=10,
        fontweight="bold",
        ha="left",
        va="bottom",
        color=COLORS["text"],
    )


def build_figure(data: pd.DataFrame) -> plt.Figure:
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
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
        }
    )

    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.65), facecolor="white")

    for ax, (x_name, y_name, title, panel) in zip(axes.flat, PAIRS, strict=True):
        pair = paired_data(data, x_name, y_name)
        ax.scatter(
            pair[x_name],
            pair[y_name],
            s=9,
            color=COLORS["point"],
            alpha=0.24,
            edgecolors="none",
            rasterized=True,
        )

        if x_name != "ph":
            ax.set_xscale("log")
        if y_name != "ph":
            ax.set_yscale("log")

        ax.set_xlabel(LABELS[x_name])
        ax.set_ylabel(LABELS[y_name])
        ax.set_title(title, pad=7)
        style_axis(ax)
        panel_label(ax, panel)

    fig.subplots_adjust(left=0.10, right=0.985, top=0.93, bottom=0.10, wspace=0.28, hspace=0.38)
    return fig


def save_outputs(fig: plt.Figure, qa: dict) -> None:
    fig.savefig(OUTPUT_STEM.with_suffix(".png"), dpi=600, facecolor="white")
    fig.savefig(OUTPUT_STEM.with_suffix(".tiff"), dpi=600, facecolor="white")
    fig.savefig(OUTPUT_STEM.with_suffix(".pdf"), facecolor="white")
    fig.savefig(OUTPUT_STEM.with_suffix(".svg"), facecolor="white")
    qa_path = OUTPUT_STEM.with_name(OUTPUT_STEM.name + "_QA.json")
    qa_path.write_text(json.dumps(qa, indent=2), encoding="utf-8")


def main() -> None:
    data, qa = load_and_validate()
    figure = build_figure(data)
    save_outputs(figure, qa)
    plt.close(figure)
    print(json.dumps(qa, indent=2))


if __name__ == "__main__":
    main()
