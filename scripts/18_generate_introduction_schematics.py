from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse, FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle


OUTPUT_DIR = Path(__file__).resolve().parents[1] / "figures" / "introduction_schematics"

COLORS = {
    "ink": "#263238",
    "muted": "#66737A",
    "line": "#B8C2C7",
    "sky": "#F7FAFB",
    "ground": "#DCE3DC",
    "bedrock": "#AAB6AF",
    "soil": "#C6D0C8",
    "water": "#4B9CB5",
    "water_dark": "#2F6C8F",
    "mine": "#B84A43",
    "groundwater": "#77679B",
    "sediment": "#C77A36",
    "tailings": "#B49B69",
    "neutral_fill": "#EEF2F3",
}


mpl.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "DejaVu Sans", "sans-serif"],
        "font.size": 8,
        "axes.linewidth": 0.8,
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "savefig.facecolor": "white",
    }
)


def save_figure(fig: plt.Figure, stem: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_DIR / f"{stem}.png", dpi=600, bbox_inches="tight", pad_inches=0.05)
    fig.savefig(OUTPUT_DIR / f"{stem}.pdf", bbox_inches="tight", pad_inches=0.05)
    fig.savefig(OUTPUT_DIR / f"{stem}.svg", bbox_inches="tight", pad_inches=0.05)
    fig.savefig(OUTPUT_DIR / f"{stem}.tiff", dpi=600, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)


def arrow(
    ax: plt.Axes,
    start: tuple[float, float],
    end: tuple[float, float],
    color: str,
    *,
    width: float = 1.5,
    style: str = "-|>",
    connectionstyle: str = "arc3",
    linestyle: str = "-",
    alpha: float = 1.0,
    zorder: int = 8,
) -> None:
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle=style,
            mutation_scale=9,
            linewidth=width,
            color=color,
            linestyle=linestyle,
            connectionstyle=connectionstyle,
            alpha=alpha,
            zorder=zorder,
        )
    )


def label_with_leader(
    ax: plt.Axes,
    text: str,
    xy: tuple[float, float],
    xytext: tuple[float, float],
    *,
    ha: str = "center",
    color: str = COLORS["ink"],
) -> None:
    ax.annotate(
        text,
        xy=xy,
        xytext=xytext,
        ha=ha,
        va="center",
        fontsize=7.4,
        color=color,
        arrowprops={
            "arrowstyle": "-",
            "color": COLORS["muted"],
            "linewidth": 0.8,
            "shrinkA": 2,
            "shrinkB": 2,
        },
        zorder=12,
    )


def rounded_box(
    ax: plt.Axes,
    x: float,
    y: float,
    width: float,
    height: float,
    text: str,
    *,
    facecolor: str,
    edgecolor: str,
    textcolor: str = COLORS["ink"],
    linewidth: float = 1.0,
    linestyle: str = "-",
    fontsize: float = 7.2,
    weight: str = "normal",
    zorder: int = 5,
) -> None:
    patch = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle="round,pad=0.025,rounding_size=0.06",
        facecolor=facecolor,
        edgecolor=edgecolor,
        linewidth=linewidth,
        linestyle=linestyle,
        zorder=zorder,
    )
    ax.add_patch(patch)
    ax.text(
        x + width / 2,
        y + height / 2,
        text,
        ha="center",
        va="center",
        fontsize=fontsize,
        color=textcolor,
        weight=weight,
        linespacing=1.15,
        zorder=zorder + 1,
    )


def _make_source_pathway_figure_cross_section() -> None:
    fig, ax = plt.subplots(figsize=(7.1, 4.15))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 7)
    ax.set_axis_off()
    ax.set_facecolor("white")

    # Cross-section context.
    land = Polygon(
        [
            (0.0, 4.45),
            (1.25, 5.15),
            (2.75, 5.58),
            (4.15, 5.05),
            (5.35, 4.55),
            (6.65, 4.12),
            (7.65, 3.05),
            (8.45, 1.68),
            (8.45, 0.0),
            (0.0, 0.0),
        ],
        closed=True,
        facecolor=COLORS["ground"],
        edgecolor=COLORS["muted"],
        linewidth=0.9,
        zorder=1,
    )
    ax.add_patch(land)
    ax.add_patch(
        Polygon(
            [(0, 0), (8.45, 0), (8.45, 1.18), (6.9, 1.45), (4.3, 1.3), (2.1, 1.7), (0, 1.55)],
            closed=True,
            facecolor=COLORS["bedrock"],
            edgecolor="none",
            alpha=0.72,
            zorder=2,
        )
    )
    ax.plot(
        [0.0, 1.25, 2.75, 4.15, 5.35, 6.65, 7.65, 8.45],
        [4.45, 5.15, 5.58, 5.05, 4.55, 4.12, 3.05, 1.68],
        color=COLORS["ink"],
        linewidth=1.15,
        zorder=4,
    )

    # Receiving river and sediment bed.
    river = Polygon(
        [(8.1, 1.48), (8.65, 1.38), (9.35, 1.5), (10.05, 1.39), (10.8, 1.5), (12, 1.41), (12, 0.55), (8.1, 0.55)],
        closed=True,
        facecolor=COLORS["water"],
        edgecolor=COLORS["water_dark"],
        linewidth=1.0,
        zorder=3,
    )
    ax.add_patch(river)
    ax.add_patch(Rectangle((8.1, 0.42), 3.9, 0.18, facecolor=COLORS["sediment"], edgecolor="none", alpha=0.55, zorder=2))

    # Mine shaft and underground workings.
    ax.add_patch(Rectangle((2.32, 2.0), 0.28, 3.42, facecolor=COLORS["ink"], edgecolor="white", linewidth=0.6, zorder=6))
    ax.add_patch(Rectangle((2.42, 1.92), 3.38, 0.28, facecolor=COLORS["ink"], edgecolor="white", linewidth=0.6, zorder=6))
    ax.add_patch(Rectangle((4.15, 2.08), 0.24, 1.05, angle=15, facecolor=COLORS["ink"], edgecolor="white", linewidth=0.5, zorder=6))

    # Adit to the valley side.
    ax.plot([5.65, 8.32], [2.05, 1.78], color=COLORS["ink"], linewidth=5.2, solid_capstyle="butt", zorder=5)
    ax.plot([5.65, 8.32], [2.05, 1.78], color="#DCE3DC", linewidth=2.0, solid_capstyle="butt", zorder=6)
    ax.add_patch(Ellipse((8.32, 1.78), 0.2, 0.33, facecolor=COLORS["ink"], edgecolor="none", zorder=7))

    # Waste-rock pile and tailings facility.
    waste = Polygon(
        [(4.65, 4.78), (5.24, 5.78), (5.96, 4.55)],
        closed=True,
        facecolor="#AFA58B",
        edgecolor=COLORS["ink"],
        linewidth=0.8,
        hatch="///",
        zorder=6,
    )
    ax.add_patch(waste)
    ax.add_patch(
        Polygon(
            [(6.08, 4.3), (6.18, 4.76), (7.42, 4.35), (7.64, 3.75), (6.42, 3.82)],
            closed=True,
            facecolor="#E0D6BD",
            edgecolor=COLORS["tailings"],
            linewidth=1.0,
            zorder=6,
        )
    )
    ax.add_patch(Rectangle((6.33, 4.16), 0.95, 0.19, facecolor=COLORS["water"], edgecolor="none", alpha=0.75, zorder=7))

    # Precipitation.
    for cx, cy, w, h in [(5.7, 6.42, 0.9, 0.38), (6.35, 6.5, 1.05, 0.48), (7.0, 6.39, 0.85, 0.36)]:
        ax.add_patch(Ellipse((cx, cy), w, h, facecolor="#DDE6EA", edgecolor=COLORS["line"], linewidth=0.7, zorder=8))
    ax.text(6.35, 6.85, "Precipitation", ha="center", va="center", fontsize=8, color=COLORS["water_dark"], weight="bold")
    for x, y_end in [(5.45, 5.86), (6.0, 5.23), (6.58, 4.9), (7.1, 4.48), (7.55, 3.75)]:
        arrow(ax, (x, 6.15), (x - 0.08, y_end), COLORS["water_dark"], width=1.0, alpha=0.75)

    # Process arrows.
    arrow(ax, (5.45, 4.6), (5.65, 2.75), COLORS["groundwater"], width=1.5)
    arrow(ax, (6.85, 3.8), (6.55, 2.45), COLORS["groundwater"], width=1.5)
    arrow(ax, (5.7, 1.4), (8.35, 1.18), COLORS["groundwater"], width=1.6, linestyle="--")
    arrow(ax, (6.95, 3.78), (8.58, 1.7), COLORS["sediment"], width=1.8, connectionstyle="arc3,rad=-0.12")
    arrow(ax, (8.28, 1.83), (9.02, 1.47), COLORS["mine"], width=2.0)
    arrow(ax, (9.12, 0.92), (10.78, 0.92), COLORS["sediment"], width=1.7, connectionstyle="arc3,rad=-0.2")

    # Direct labels and leaders.
    label_with_leader(ax, "Mine shaft", (2.45, 5.33), (1.25, 5.92), ha="left")
    label_with_leader(ax, "Underground\nworkings", (3.15, 2.08), (0.45, 2.5), ha="left")
    label_with_leader(ax, "Waste-rock pile", (5.28, 5.45), (4.52, 6.12))
    label_with_leader(ax, "Tailings facility", (6.85, 4.36), (7.7, 5.3))
    ax.text(5.08, 3.25, "Leaching", ha="center", va="center", fontsize=7.2, color=COLORS["groundwater"], weight="bold")
    ax.text(6.12, 2.55, "Seepage", ha="center", va="center", fontsize=7.2, color=COLORS["groundwater"], weight="bold")
    ax.text(7.32, 3.05, "Runoff /\nerosion", ha="center", va="center", fontsize=7.0, color=COLORS["sediment"], weight="bold", linespacing=1.05)
    ax.text(5.95, 1.02, "Groundwater transport", ha="center", va="center", fontsize=7.0, color=COLORS["groundwater"], weight="bold")
    ax.text(8.4, 2.18, "Adit drainage", ha="center", va="bottom", fontsize=7.2, color=COLORS["mine"], weight="bold")
    ax.text(10.05, 1.82, "Receiving river", ha="center", va="bottom", fontsize=8, color=COLORS["water_dark"], weight="bold")
    ax.text(10.05, 1.06, "Dissolved and particulate\nPb, Zn and Cu", ha="center", va="center", fontsize=7.3, color="white", weight="bold", linespacing=1.15, zorder=10)
    ax.text(10.0, 0.29, "Sediment storage / remobilisation", ha="center", va="center", fontsize=6.6, color=COLORS["sediment"], weight="bold")

    save_figure(fig, "Figure_1_1_mine_pollution_pathways_cross_section")


def make_source_pathway_figure() -> None:
    fig, ax = plt.subplots(figsize=(7.1, 3.1))
    ax.set_xlim(0, 12)
    ax.set_ylim(0.85, 5.45)
    ax.set_axis_off()
    ax.set_facecolor("white")

    headers = [
        (1.85, "Abandoned mine features"),
        (5.75, "Mobilisation and transport"),
        (9.95, "Receiving river"),
    ]
    for x, text in headers:
        ax.text(x, 5.05, text, ha="center", va="center", fontsize=8.1, color=COLORS["ink"], weight="bold")

    row_y = [3.95, 2.82, 1.69]

    source_labels = [
        "Mine workings, adits\nand shafts",
        "Waste-rock piles",
        "Tailings facilities",
    ]
    source_fills = ["#F5E5E3", "#F5EBDD", "#F2EEDF"]
    for y, text, fill in zip(row_y, source_labels, source_fills):
        rounded_box(
            ax,
            0.58,
            y - 0.42,
            2.55,
            0.84,
            text,
            facecolor=fill,
            edgecolor="none",
            textcolor=COLORS["ink"],
            fontsize=7.2,
            weight="bold",
            linewidth=0,
        )

    process_labels = [
        "Mine drainage",
        "Leaching and\ngroundwater seepage",
        "Runoff and erosion",
    ]
    process_colors = [COLORS["mine"], COLORS["groundwater"], COLORS["sediment"]]
    process_fills = ["#F5E5E3", "#ECE8F4", "#F7E8DA"]
    for y, text, text_color, fill in zip(row_y, process_labels, process_colors, process_fills):
        rounded_box(
            ax,
            4.34,
            y - 0.42,
            2.82,
            0.84,
            text,
            facecolor=fill,
            edgecolor="none",
            textcolor=text_color,
            fontsize=7.1,
            weight="bold",
            linewidth=0,
        )

    transfer_y = sum(row_y) / len(row_y)
    arrow(ax, (3.35, transfer_y), (4.10, transfer_y), COLORS["ink"], width=1.4)
    arrow(ax, (7.40, transfer_y), (8.30, transfer_y), COLORS["ink"], width=1.4)

    river_x, river_y, river_w, river_h = 8.50, 1.27, 2.95, 3.22
    ax.add_patch(
        FancyBboxPatch(
            (river_x, river_y),
            river_w,
            river_h,
            boxstyle="round,pad=0.02,rounding_size=0.06",
            facecolor="#E4F1F4",
            edgecolor="none",
            linewidth=0,
            zorder=3,
        )
    )
    ax.add_patch(
        Rectangle(
            (river_x, river_y),
            river_w,
            0.72,
            facecolor="#E9C69E",
            edgecolor="none",
            linewidth=0,
            zorder=4,
        )
    )
    ax.text(9.98, 3.78, "Dissolved Pb, Zn and Cu", ha="center", va="center", fontsize=7.3, color=COLORS["water_dark"], weight="bold", zorder=6)
    ax.text(9.98, 2.78, "Particulate metals", ha="center", va="center", fontsize=7.3, color=COLORS["water_dark"], weight="bold", zorder=6)
    ax.text(9.98, 1.63, "Contaminated sediment", ha="center", va="center", fontsize=7.0, color="#8A541F", weight="bold", zorder=6)
    arrow(ax, (11.12, 1.98), (11.12, 2.46), COLORS["sediment"], width=1.1, style="<->")
    ax.text(10.88, 2.22, "storage /\nremobilisation", ha="right", va="center", fontsize=6.3, color=COLORS["sediment"], linespacing=1.05, zorder=7)

    save_figure(fig, "Figure_1_1_mine_pollution_pathways")


def add_river(ax: plt.Axes, x0: float, x1: float, y0: float, y1: float, label: str) -> None:
    xs = [x0, x0 + 0.8, x0 + 1.6, x0 + 2.4, x0 + 3.2, x1]
    top = [y1, y1 - 0.06, y1 + 0.04, y1 - 0.04, y1 + 0.05, y1]
    coords = list(zip(xs, top)) + [(x1, y0), (x0, y0)]
    ax.add_patch(Polygon(coords, closed=True, facecolor=COLORS["water"], edgecolor=COLORS["water_dark"], linewidth=0.9, zorder=3))
    ax.text((x0 + x1) / 2, (y0 + y1) / 2, label, ha="center", va="center", fontsize=7.6, color="white", weight="bold", zorder=4)


def make_flow_concept_figure() -> None:
    fig, ax = plt.subplots(figsize=(7.1, 4.15))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 7)
    ax.set_axis_off()
    ax.set_facecolor("white")

    ax.add_patch(Rectangle((0.12, 0.52), 5.72, 6.18, facecolor="#F5F8FA", edgecolor=COLORS["line"], linewidth=0.9, zorder=0))
    ax.add_patch(Rectangle((6.16, 0.52), 5.72, 6.18, facecolor="#FAF7F3", edgecolor=COLORS["line"], linewidth=0.9, zorder=0))

    ax.text(0.3, 6.47, "a", ha="left", va="center", fontsize=9, weight="bold", color=COLORS["ink"])
    ax.text(3.0, 6.47, "Possible lower-flow configuration", ha="center", va="center", fontsize=9, weight="bold", color=COLORS["ink"])
    ax.text(6.34, 6.47, "b", ha="left", va="center", fontsize=9, weight="bold", color=COLORS["ink"])
    ax.text(9.03, 6.47, "Possible higher-flow configuration", ha="center", va="center", fontsize=9, weight="bold", color=COLORS["ink"])

    # Lower-flow source balance.
    rounded_box(ax, 0.42, 5.02, 1.62, 0.83, "Mine drainage", facecolor="#F3DEDC", edgecolor=COLORS["mine"], textcolor=COLORS["mine"], weight="bold", fontsize=6.9)
    rounded_box(ax, 2.17, 5.02, 1.62, 0.83, "Groundwater\nseepage", facecolor="#E9E5F2", edgecolor=COLORS["groundwater"], textcolor=COLORS["groundwater"], weight="bold", fontsize=6.9)
    rounded_box(ax, 3.92, 5.02, 1.62, 0.83, "Runoff / sediment\nmobilisation", facecolor=COLORS["neutral_fill"], edgecolor=COLORS["line"], textcolor=COLORS["muted"], linestyle="--", fontsize=6.5)
    rounded_box(ax, 1.0, 3.42, 3.95, 0.88, "Persistent inputs may form a larger\nproportion of river flow", facecolor="#E5F0F4", edgecolor=COLORS["water_dark"], textcolor=COLORS["water_dark"], weight="bold", fontsize=7.5)
    arrow(ax, (1.23, 5.0), (2.05, 4.33), COLORS["mine"], width=1.4)
    arrow(ax, (2.98, 5.0), (2.98, 4.33), COLORS["groundwater"], width=1.4)
    arrow(ax, (4.73, 5.0), (3.92, 4.33), COLORS["line"], width=1.0, linestyle="--", alpha=0.9)
    rounded_box(ax, 1.46, 2.24, 3.05, 0.62, "Reduced dilution", facecolor="white", edgecolor=COLORS["water_dark"], textcolor=COLORS["water_dark"], fontsize=7.8, weight="bold")
    arrow(ax, (2.98, 3.4), (2.98, 2.88), COLORS["water_dark"], width=1.5)
    arrow(ax, (2.98, 2.22), (2.98, 1.78), COLORS["water_dark"], width=1.5)
    add_river(ax, 0.55, 5.45, 0.9, 1.62, "Lower river flow")

    # Higher-flow source balance.
    rounded_box(ax, 6.46, 5.02, 1.62, 0.83, "Mine drainage", facecolor=COLORS["neutral_fill"], edgecolor=COLORS["line"], textcolor=COLORS["muted"], linestyle="--", fontsize=6.9)
    rounded_box(ax, 8.21, 5.02, 1.62, 0.83, "Runoff / waste-rock\nwash-off", facecolor="#E5F0F4", edgecolor=COLORS["water_dark"], textcolor=COLORS["water_dark"], weight="bold", fontsize=6.5)
    rounded_box(ax, 9.96, 5.02, 1.62, 0.83, "Sediment\nremobilisation", facecolor="#F6E7D9", edgecolor=COLORS["sediment"], textcolor=COLORS["sediment"], weight="bold", fontsize=6.8)
    rounded_box(ax, 7.04, 3.42, 3.95, 0.88, "Dilution and pollutant mobilisation\ncan occur together", facecolor="#F2ECE5", edgecolor=COLORS["sediment"], textcolor=COLORS["ink"], weight="bold", fontsize=7.5)
    arrow(ax, (7.27, 5.0), (8.08, 4.33), COLORS["line"], width=1.0, linestyle="--")
    arrow(ax, (9.02, 5.0), (9.02, 4.33), COLORS["water_dark"], width=1.5)
    arrow(ax, (10.77, 5.0), (9.95, 4.33), COLORS["sediment"], width=1.5)
    rounded_box(ax, 7.5, 2.17, 3.05, 0.76, "More connected\nflow pathways", facecolor="white", edgecolor=COLORS["sediment"], textcolor=COLORS["sediment"], fontsize=7.0, weight="bold")
    arrow(ax, (9.02, 3.4), (9.02, 2.88), COLORS["sediment"], width=1.5)
    arrow(ax, (9.02, 2.15), (9.02, 1.92), COLORS["sediment"], width=1.5)
    add_river(ax, 6.58, 11.46, 0.72, 1.82, "Higher river flow")

    save_figure(fig, "Figure_1_2_flow_process_concept")


def make_pollution_source_screening_figure() -> None:
    fig, ax = plt.subplots(figsize=(7.1, 3.75))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 6.4)
    ax.set_axis_off()
    ax.set_facecolor("white")

    # Two source families capture the distinction in Section 1.1 without
    # implying that a pathway belongs exclusively to one flow condition.
    ax.add_patch(
        FancyBboxPatch(
            (0.45, 2.82),
            5.25,
            2.95,
            boxstyle="round,pad=0.02,rounding_size=0.07",
            facecolor="#F5F8FA",
            edgecolor=COLORS["line"],
            linewidth=1.0,
            zorder=1,
        )
    )
    ax.add_patch(
        FancyBboxPatch(
            (6.3, 2.82),
            5.25,
            2.95,
            boxstyle="round,pad=0.02,rounding_size=0.07",
            facecolor="#FAF7F3",
            edgecolor=COLORS["line"],
            linewidth=1.0,
            zorder=1,
        )
    )

    ax.text(3.08, 5.43, "Persistent and subsurface\npathways", ha="center", va="center", fontsize=8.1, color=COLORS["ink"], weight="bold", linespacing=1.05)
    ax.text(8.92, 5.43, "Rainfall- and flow-responsive\npathways", ha="center", va="center", fontsize=8.1, color=COLORS["ink"], weight="bold", linespacing=1.05)
    ax.plot([0.8, 5.35], [5.08, 5.08], color=COLORS["line"], linewidth=0.9)
    ax.plot([6.65, 11.2], [5.08, 5.08], color=COLORS["line"], linewidth=0.9)

    rounded_box(ax, 0.8, 4.02, 1.35, 0.72, "Adit\ndrainage", facecolor="#F5E5E3", edgecolor=COLORS["mine"], textcolor=COLORS["mine"], fontsize=6.9, weight="bold")
    rounded_box(ax, 2.4, 4.02, 1.35, 0.72, "Tailings\nseepage", facecolor="#ECE8F4", edgecolor=COLORS["groundwater"], textcolor=COLORS["groundwater"], fontsize=6.9, weight="bold")
    rounded_box(ax, 4.0, 4.02, 1.35, 0.72, "Diffuse\ngroundwater", facecolor="#E4F1F4", edgecolor=COLORS["water_dark"], textcolor=COLORS["water_dark"], fontsize=6.8, weight="bold")

    rounded_box(ax, 6.72, 3.86, 2.0, 0.92, "Waste-rock\nerosion", facecolor="#F7E8DA", edgecolor=COLORS["sediment"], textcolor=COLORS["sediment"], fontsize=7.1, weight="bold")
    rounded_box(ax, 9.12, 3.86, 2.0, 0.92, "Contaminated\nsediment\nremobilisation", facecolor="#F3E4D3", edgecolor="#9A642F", textcolor="#8A541F", fontsize=6.2, weight="bold")

    ax.text(3.08, 3.28, "Continuous or slowly\nvarying contributions", ha="center", va="center", fontsize=6.8, color=COLORS["muted"], linespacing=1.05)
    ax.text(8.92, 3.28, "May intensify during rainfall\nor higher flow", ha="center", va="center", fontsize=6.8, color=COLORS["muted"], linespacing=1.05)

    rounded_box(
        ax,
        3.45,
        1.54,
        5.1,
        0.94,
        "Observed river concentration reflects\na mixture of pathways",
        facecolor="#E5F0F4",
        edgecolor=COLORS["water_dark"],
        textcolor=COLORS["water_dark"],
        fontsize=7.3,
        weight="bold",
        linewidth=1.1,
    )
    arrow(ax, (3.08, 2.8), (4.7, 2.51), COLORS["water_dark"], width=1.4, connectionstyle="arc3,rad=0.08")
    arrow(ax, (8.92, 2.8), (7.3, 2.51), COLORS["sediment"], width=1.4, connectionstyle="arc3,rad=-0.08")

    rounded_box(
        ax,
        1.28,
        0.23,
        9.44,
        0.82,
        "Concentration alone does not determine annual metal load,\necological risk or remediation tractability.",
        facecolor="#F1F3F4",
        edgecolor=COLORS["line"],
        textcolor=COLORS["ink"],
        fontsize=6.9,
        weight="bold",
        linewidth=0.9,
    )
    arrow(ax, (6.0, 1.52), (6.0, 1.08), COLORS["ink"], width=1.4)

    save_figure(fig, "Figure_1_2_pollution_source_categories")


def main() -> None:
    make_source_pathway_figure()
    make_pollution_source_screening_figure()
    print(f"Created figures in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
