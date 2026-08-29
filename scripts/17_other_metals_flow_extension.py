from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy.stats import spearmanr


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"
RESULTS = ROOT / "results" / "7.7_other_metals"

LONG_PARQUET = PROCESSED / "water_quality_selected_long.parquet"
MINE_SUMMARY = PROCESSED / "mine_related_stations_summary.csv"
DEVIATING_RECORDS = PROCESSED / "raw_deviating_target_records.csv"
DAILY_FLOW = PROCESSED / "nrfa_gdf_matched_daily_flow.csv"
NRFA_METADATA = RAW / "river_flow" / "nrfa_station_metadata_all.csv"
WQ_STATIONS = RAW / "stations" / "nrw_water_quality_archive_stations.csv"
FINAL_SITES = ROOT / "results" / "7.6_site_profiles" / "7.6_Site_Summary.csv"
FINAL_SAMPLES = ROOT / "results" / "7.6_site_profiles" / "7.6_Sample_Data.csv"
PBZN_WINDOWS = ROOT / "results" / "7.5_sensitivity" / "7.5_Flow_Window_Stations.csv"

LOW_FLOW_PERCENTILE = 0.25
PAIR_DEFINITIONS = {
    "Pb/Zn": ("lead", "zinc"),
    "Cu/Zn": ("copper", "zinc"),
    "Pb/Cu": ("lead", "copper"),
}
SYMBOLS = {"lead": "Pb", "zinc": "Zn", "copper": "Cu"}


def percentile_of_score(reference: np.ndarray, values: np.ndarray) -> np.ndarray:
    ordered = np.sort(reference)
    return np.searchsorted(ordered, values, side="right") / len(ordered)


def bh_adjust(p_values: pd.Series) -> pd.Series:
    result = pd.Series(np.nan, index=p_values.index, dtype=float)
    valid = p_values.dropna().sort_values()
    if valid.empty:
        return result
    n = len(valid)
    adjusted = valid.to_numpy(float) * n / np.arange(1, n + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    result.loc[valid.index] = np.minimum(adjusted, 1.0)
    return result


def load_exact_long() -> pd.DataFrame:
    mine_ids = set(pd.read_csv(MINE_SUMMARY, usecols=["station_id"])["station_id"].astype(str))
    parameters = sorted({parameter for pair in PAIR_DEFINITIONS.values() for parameter in pair})
    long = pd.read_parquet(
        LONG_PARQUET,
        columns=["station_id", "station_name", "sample_date", "canonical_parameter", "value_standardised", "qualifier"],
    )
    long["station_id"] = long["station_id"].astype(str)
    long = long[
        long["station_id"].isin(mine_ids)
        & long["canonical_parameter"].isin(parameters)
    ].copy()
    long["sample_date"] = pd.to_datetime(long["sample_date"])

    deviations = pd.read_csv(
        DEVIATING_RECORDS,
        usecols=["station_number", "sampling_datetime", "canonical_parameter"],
    ).rename(columns={"station_number": "station_id", "sampling_datetime": "sample_date"})
    deviations["station_id"] = deviations["station_id"].astype(str)
    deviations["sample_date"] = pd.to_datetime(deviations["sample_date"])
    deviations = deviations.drop_duplicates(["station_id", "sample_date", "canonical_parameter"])
    long = long.merge(
        deviations.assign(_deviating=True),
        on=["station_id", "sample_date", "canonical_parameter"],
        how="left",
    )
    long = long[long["_deviating"].isna()].copy()
    long["value"] = pd.to_numeric(long["value_standardised"], errors="coerce")
    qualifier = long["qualifier"].fillna("").astype(str).str.strip()
    long["censored"] = qualifier.isin(["<", ">"])
    grouped = (
        long.groupby(["station_id", "station_name", "sample_date", "canonical_parameter"], dropna=False)
        .agg(value=("value", "mean"), any_censored=("censored", "max"))
        .reset_index()
    )
    grouped = grouped[(grouped["value"] > 0) & ~grouped["any_censored"]].copy()
    return grouped


def make_pair(exact: pd.DataFrame, pair_name: str) -> pd.DataFrame:
    numerator, denominator = PAIR_DEFINITIONS[pair_name]
    keys = ["station_id", "station_name", "sample_date"]
    wide = exact[exact["canonical_parameter"].isin([numerator, denominator])].pivot(
        index=keys, columns="canonical_parameter", values="value"
    )
    pair = wide[[numerator, denominator]].dropna().reset_index()
    pair = pair[(pair[numerator] > 0) & (pair[denominator] > 0)].copy()
    pair["pair"] = pair_name
    pair["numerator_parameter"] = numerator
    pair["denominator_parameter"] = denominator
    pair["numerator_value"] = pair[numerator]
    pair["denominator_value"] = pair[denominator]
    pair["ratio"] = pair[numerator] / pair[denominator]
    pair["sample_day"] = pd.to_datetime(pair["sample_date"]).dt.floor("D")

    numerator_high = float(pair["numerator_value"].quantile(0.75))
    denominator_low = float(pair["denominator_value"].quantile(0.25))
    ratio_high = float(pair["ratio"].quantile(0.90))
    pair["high_numerator"] = pair["numerator_value"] >= numerator_high
    pair["low_denominator"] = pair["denominator_value"] <= denominator_low
    pair["high_ratio"] = pair["ratio"] >= ratio_high
    pair.attrs["thresholds"] = {
        "numerator_high": numerator_high,
        "denominator_low": denominator_low,
        "ratio_high": ratio_high,
    }
    return pair


def available_gauges(flows: pd.DataFrame) -> pd.DataFrame:
    ids = set(flows["nrfa_station_id"].dropna().astype(int))
    metadata = pd.read_csv(NRFA_METADATA)
    metadata = metadata[metadata["nrfa_station_id"].isin(ids)].dropna(subset=["easting", "northing"]).copy()
    return metadata


def nearest_matches(station_ids: set[str], gauges: pd.DataFrame) -> pd.DataFrame:
    stations = pd.read_csv(WQ_STATIONS)
    stations["station_number"] = stations["station_number"].astype(str)
    stations = (
        stations[stations["station_number"].isin(station_ids)]
        .dropna(subset=["easting", "northing"])
        .drop_duplicates("station_number")
        .copy()
    )
    gauge_xy = gauges[["easting", "northing"]].to_numpy(float)
    rows = []
    for _, station in stations.iterrows():
        distances = np.sqrt(((gauge_xy - np.array([station.easting, station.northing])) ** 2).sum(axis=1))
        nearest_index = int(np.argmin(distances))
        gauge = gauges.iloc[nearest_index]
        rows.append(
            {
                "station_id": station.station_number,
                "station_type": station.station_type,
                "wfd_c2_mgt_catchment_name": station.wfd_c2_mgt_catchment_name,
                "nrfa_station_id": int(gauge.nrfa_station_id),
                "nrfa_station_name": gauge.nrfa_station_name,
                "nrfa_river": gauge.river,
                "flow_match_distance_km": float(distances[nearest_index] / 1000),
            }
        )
    result = pd.DataFrame(rows)
    result["within_20km_flow_match"] = result["flow_match_distance_km"] <= 20
    return result


def add_flow(pair: pd.DataFrame, matches: pd.DataFrame, flows: pd.DataFrame) -> pd.DataFrame:
    data = pair.merge(matches, on="station_id", how="left")
    data = data[data["within_20km_flow_match"].fillna(False)].copy()
    data = data.merge(
        flows[["nrfa_station_id", "flow_date", "flow_m3s"]],
        left_on=["nrfa_station_id", "sample_day"],
        right_on=["nrfa_station_id", "flow_date"],
        how="left",
    )
    data["flow_percentile"] = np.nan
    references = {
        station_id: group.loc[group["flow_m3s"].ge(0), "flow_m3s"].dropna().to_numpy(float)
        for station_id, group in flows.groupby("nrfa_station_id")
    }
    for station_id, indices in data.groupby("nrfa_station_id", dropna=True).groups.items():
        reference = references.get(station_id, np.array([]))
        valid = data.loc[indices, "flow_m3s"].notna()
        if len(reference) == 0 or not valid.any():
            continue
        valid_indices = valid[valid].index
        data.loc[valid_indices, "flow_percentile"] = percentile_of_score(
            reference, data.loc[valid_indices, "flow_m3s"].to_numpy(float)
        )
    data["has_flow"] = data["flow_percentile"].notna()
    data["low_flow"] = data["flow_percentile"] <= LOW_FLOW_PERCENTILE
    data["primary_event"] = data["low_flow"] & data["high_ratio"]
    data["strict_event"] = data["low_flow"] & data["high_numerator"] & data["low_denominator"]
    return data


def station_summary(data: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for keys, group in data.groupby(
        ["pair", "station_id", "station_name", "station_type", "wfd_c2_mgt_catchment_name", "nrfa_station_id", "nrfa_station_name", "flow_match_distance_km"],
        dropna=False,
    ):
        with_flow = group[group["has_flow"]]
        n_flow = len(with_flow)
        n_events = int(with_flow["primary_event"].sum())
        n_strict = int(with_flow["strict_event"].sum())
        event_prop = n_events / n_flow if n_flow else np.nan
        rows.append(
            {
                **dict(zip(["pair", "station_id", "station_name", "station_type", "wfd_c2_mgt_catchment_name", "nrfa_station_id", "nrfa_station_name", "flow_match_distance_km"], keys)),
                "n_pairs": len(group),
                "n_with_flow": n_flow,
                "n_primary_events": n_events,
                "n_strict_events": n_strict,
                "event_proportion_all_flow": event_prop,
                "median_ratio": group["ratio"].median(),
            }
        )
    summary = pd.DataFrame(rows)
    summary["systematic_candidate"] = (
        summary["n_with_flow"].ge(3)
        & (
            summary["n_strict_events"].ge(2)
            | summary["n_primary_events"].ge(3)
            | (summary["n_primary_events"].ge(2) & summary["event_proportion_all_flow"].ge(0.30))
        )
    )
    return summary


def overall_summary(data: pd.DataFrame, station_table: pd.DataFrame, thresholds: dict) -> dict:
    with_flow = data[data["has_flow"]].copy()
    pair_rho, pair_p = spearmanr(data["numerator_value"], data["denominator_value"], nan_policy="omit")
    ratio_rho, ratio_p = spearmanr(with_flow["ratio"], with_flow["flow_percentile"], nan_policy="omit")
    low = with_flow[with_flow["low_flow"]]
    normal = with_flow[~with_flow["low_flow"]]
    return {
        "pair": data["pair"].iloc[0],
        "n_exact_pairs": len(data),
        "n_pair_stations": data["station_id"].nunique(),
        "n_with_same_day_flow": len(with_flow),
        "n_flow_stations": with_flow["station_id"].nunique(),
        "spearman_pair_rho": pair_rho,
        "spearman_pair_p": pair_p,
        "spearman_ratio_flow_rho": ratio_rho,
        "spearman_ratio_flow_p": ratio_p,
        "median_ratio": data["ratio"].median(),
        "median_ratio_low_flow": low["ratio"].median(),
        "median_ratio_normal_high_flow": normal["ratio"].median(),
        "low_to_normal_ratio_fold": low["ratio"].median() / normal["ratio"].median(),
        "n_primary_events": int(with_flow["primary_event"].sum()),
        "n_strict_events": int(with_flow["strict_event"].sum()),
        "n_candidates": int(station_table["systematic_candidate"].sum()),
        **thresholds,
    }


def add_manual_flow(pair: pd.DataFrame, final_samples: pd.DataFrame) -> pd.DataFrame:
    # Restrict the extension to dates already used in the manually validated final
    # Pb/Zn analysis. This asks whether Cu adds information to the established result
    # without introducing a second, unreviewed hydrological matching population.
    context_columns = [
        "station_id", "sample_date", "system", "manual_nrfa_id", "manual_nrfa_name",
        "manual_flow_m3s", "manual_flow_percentile",
    ]
    context = final_samples[context_columns].drop_duplicates(["station_id", "sample_date"])
    data = pair.merge(context, on=["station_id", "sample_date"], how="inner")
    data["manual_low_flow"] = data["manual_flow_percentile"] <= LOW_FLOW_PERCENTILE
    return data


def final_site_context(manual_data: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for keys, group in manual_data.groupby(["pair", "system", "station_id", "station_name"], dropna=False):
        with_flow = group[group["manual_flow_percentile"].notna()].copy()
        low = with_flow[with_flow["manual_low_flow"]]
        normal = with_flow[~with_flow["manual_low_flow"]]
        rho = p = np.nan
        if len(with_flow) >= 3 and with_flow["ratio"].nunique() > 1 and with_flow["manual_flow_percentile"].nunique() > 1:
            rho, p = spearmanr(with_flow["ratio"], with_flow["manual_flow_percentile"], nan_policy="omit")

        def fold(column):
            low_median = low[column].median()
            normal_median = normal[column].median()
            return low_median / normal_median if pd.notna(normal_median) and normal_median != 0 else np.nan

        rows.append(
            {
                "pair": keys[0], "system": keys[1], "station_id": keys[2], "station_name": keys[3],
                "n_exact_pairs": len(group), "n_with_manual_flow": len(with_flow), "n_low_flow": len(low),
                "spearman_ratio_vs_flow_rho": rho, "spearman_ratio_vs_flow_p": p,
                "low_to_normal_numerator_fold": fold("numerator_value"),
                "low_to_normal_denominator_fold": fold("denominator_value"),
                "low_to_normal_ratio_fold": fold("ratio"),
            }
        )
    result = pd.DataFrame(rows)
    result["spearman_ratio_vs_flow_fdr_q"] = np.nan
    for pair, indices in result.groupby("pair").groups.items():
        result.loc[indices, "spearman_ratio_vs_flow_fdr_q"] = bh_adjust(
            result.loc[indices, "spearman_ratio_vs_flow_p"]
        )
    return result


def pbzn_event_copper_context(exact: pd.DataFrame, final_samples: pd.DataFrame) -> pd.DataFrame:
    keys = ["station_id", "station_name", "sample_date"]
    wide = exact.pivot(index=keys, columns="canonical_parameter", values="value")
    triples = wide[["lead", "zinc", "copper"]].dropna().reset_index()
    triples["pb_zn_ratio"] = triples["lead"] / triples["zinc"]
    triples["cu_zn_ratio"] = triples["copper"] / triples["zinc"]
    triples["pb_cu_ratio"] = triples["lead"] / triples["copper"]
    context = final_samples[
        ["station_id", "sample_date", "system", "primary_event", "manual_low_flow"]
    ].drop_duplicates(["station_id", "sample_date"])
    triples = triples.merge(context, on=["station_id", "sample_date"], how="inner")
    rows = []
    measures = ["lead", "zinc", "copper", "pb_zn_ratio", "cu_zn_ratio", "pb_cu_ratio"]
    for keys, group in triples.groupby(["system", "station_id", "station_name"], dropna=False):
        event = group[group["primary_event"]]
        normal = group[~group["manual_low_flow"]]
        row = {
            "system": keys[0], "station_id": keys[1], "station_name": keys[2],
            "n_exact_pb_zn_cu": len(group), "n_pbzn_events_with_cu": len(event),
            "n_normal_high_flow_with_cu": len(normal),
        }
        for measure in measures:
            event_median = event[measure].median()
            normal_median = normal[measure].median()
            row[f"event_median_{measure}"] = event_median
            row[f"normal_median_{measure}"] = normal_median
            row[f"event_to_normal_{measure}_fold"] = (
                event_median / normal_median
                if pd.notna(event_median) and pd.notna(normal_median) and normal_median != 0
                else np.nan
            )
        rows.append(row)
    return pd.DataFrame(rows)


def make_plots(all_flow: pd.DataFrame, context: pd.DataFrame):
    sns.set_theme(style="whitegrid", context="paper")
    plt.rcParams.update({"font.family": "Arial", "font.size": 9, "axes.titlesize": 11, "axes.labelsize": 9})
    colors = {"Pb/Zn": "#365F7D", "Cu/Zn": "#2F7D5A", "Pb/Cu": "#B1583E"}

    fig, axes = plt.subplots(1, 3, figsize=(10.8, 3.4), sharex=True)
    for ax, pair_name in zip(axes, PAIR_DEFINITIONS):
        data = all_flow[(all_flow["pair"] == pair_name) & all_flow["flow_percentile"].notna()].copy()
        ax.scatter(data["flow_percentile"] * 100, data["ratio"], s=7, alpha=0.20, color=colors[pair_name], linewidth=0)
        ax.set_yscale("log")
        rho, p = spearmanr(data["ratio"], data["flow_percentile"])
        ax.axvspan(0, 25, color="#DDE8EA", alpha=0.65)
        ax.set_title(f"{pair_name}: rho={rho:.3f}, p={p:.3g}")
        ax.set_xlabel("Matched flow percentile (%)")
        ax.set_ylabel(f"{pair_name} ratio")
    fig.suptitle("Other-metal ratio responses do not share one regional flow pattern", y=1.02, fontsize=12, fontweight="bold")
    fig.tight_layout()
    fig.savefig(RESULTS / "7.7_Ratio_vs_Flow.png", dpi=240, bbox_inches="tight")
    plt.close(fig)

    plot_context = context.copy()
    plot_context.loc[plot_context["n_with_manual_flow"] < 3, "low_to_normal_ratio_fold"] = np.nan
    plot = plot_context.pivot(index="station_id", columns="pair", values="low_to_normal_ratio_fold").reindex(columns=list(PAIR_DEFINITIONS))
    fig, ax = plt.subplots(figsize=(7.2, 5.0))
    sns.heatmap(plot, annot=True, fmt=".2f", center=1, cmap="vlag", vmin=0.35, vmax=2.5, linewidths=0.5, cbar_kws={"label": "Low-flow / normal-high-flow median ratio"}, ax=ax)
    ax.set_xlabel("")
    ax.set_ylabel("Final robust station")
    ax.set_title("Other ratios add site-specific context to the nine Pb/Zn candidates", fontweight="bold")
    fig.tight_layout()
    fig.savefig(RESULTS / "7.7_Final_Nine_Ratio_Folds.png", dpi=240, bbox_inches="tight")
    plt.close(fig)


def export_excel(sheets: dict[str, pd.DataFrame]):
    path = RESULTS / "7.7_Other_Metals.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, index=False, sheet_name=name[:31])
            ws = writer.book[name[:31]]
            ws.freeze_panes = "A2"
            for column in ws.columns:
                values = [str(cell.value) if cell.value is not None else "" for cell in column[:250]]
                width = min(max(max(map(len, values), default=0) + 2, 11), 46)
                ws.column_dimensions[column[0].column_letter].width = width


def main():
    RESULTS.mkdir(parents=True, exist_ok=True)
    exact = load_exact_long()
    flows = pd.read_csv(DAILY_FLOW, parse_dates=["flow_date"])
    flows["nrfa_station_id"] = flows["nrfa_station_id"].astype(int)
    gauges = available_gauges(flows)
    final_sites = pd.read_csv(FINAL_SITES)
    final_sites["station_id"] = final_sites["station_id"].astype(str)
    final_samples = pd.read_csv(FINAL_SAMPLES, parse_dates=["sample_date"])
    final_samples["station_id"] = final_samples["station_id"].astype(str)

    pair_frames = {name: make_pair(exact, name) for name in PAIR_DEFINITIONS}
    all_station_ids = set().union(*(set(frame["station_id"]) for frame in pair_frames.values()))
    matches = nearest_matches(all_station_ids, gauges)

    flow_frames = []
    station_frames = []
    overall_rows = []
    manual_frames = []
    for name, pair in pair_frames.items():
        flow = add_flow(pair, matches, flows)
        stations = station_summary(flow)
        overall_rows.append(overall_summary(flow, stations, pair.attrs["thresholds"]))
        flow_frames.append(flow)
        station_frames.append(stations)
        manual_frames.append(add_manual_flow(pair, final_samples))

    all_flow = pd.concat(flow_frames, ignore_index=True)
    all_stations = pd.concat(station_frames, ignore_index=True)
    overall = pd.DataFrame(overall_rows)
    manual = pd.concat(manual_frames, ignore_index=True)
    context = final_site_context(manual)
    event_copper = pbzn_event_copper_context(exact, final_samples)

    pbzn_windows = pd.read_csv(PBZN_WINDOWS)
    pbzn_same = set(
        pbzn_windows.loc[
            pbzn_windows["method"].eq("same_day") & pbzn_windows["systematic_candidate"], "station_id"
        ].astype(str)
    )
    robust = set(final_sites["station_id"])
    overlap_rows = []
    candidate_sets = {}
    for pair_name, group in all_stations.groupby("pair"):
        candidate_sets[pair_name] = set(group.loc[group["systematic_candidate"], "station_id"].astype(str))
    for pair_name, candidates in candidate_sets.items():
        overlap_rows.append(
            {
                "pair": pair_name,
                "n_candidates": len(candidates),
                "overlap_with_pbzn_automatic_10": len(candidates & pbzn_same),
                "overlap_with_final_robust_9": len(candidates & robust),
                "candidate_station_ids": "; ".join(sorted(candidates)),
            }
        )
    overlap = pd.DataFrame(overlap_rows)

    candidates = all_stations[all_stations["systematic_candidate"]].sort_values(
        ["pair", "n_primary_events", "n_strict_events"], ascending=[True, False, False]
    )
    overall.to_csv(RESULTS / "7.7_Overall_Summary.csv", index=False)
    overlap.to_csv(RESULTS / "7.7_Candidate_Overlap.csv", index=False)
    candidates.to_csv(RESULTS / "7.7_Candidates.csv", index=False)
    context.to_csv(RESULTS / "7.7_Final_Nine_Site_Context.csv", index=False)
    event_copper.to_csv(RESULTS / "7.7_PbZn_Event_Copper_Context.csv", index=False)
    all_flow.to_csv(RESULTS / "7.7_All_Pair_Flow_Samples.csv", index=False)
    matches.to_csv(RESULTS / "7.7_Flow_Station_Matches.csv", index=False)
    export_excel({
        "overall_summary": overall,
        "candidate_overlap": overlap,
        "candidates": candidates,
        "final_nine_context": context,
        "pbzn_event_copper": event_copper,
        "station_summary": all_stations,
    })
    make_plots(all_flow, context)

    print(overall.to_string(index=False))
    print("\nCandidate overlap:")
    print(overlap.to_string(index=False))
    print("\nS83020 context:")
    print(context[context["station_id"].eq("S83020")].to_string(index=False))
    print("\nS83020 Pb/Zn-event copper context:")
    print(event_copper[event_copper["station_id"].eq("S83020")].to_string(index=False))


if __name__ == "__main__":
    main()
