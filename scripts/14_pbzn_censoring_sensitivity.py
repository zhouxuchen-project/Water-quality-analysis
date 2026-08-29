from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
RESULTS = ROOT / "results" / "7.5_sensitivity"

LONG_PARQUET = PROCESSED / "water_quality_selected_long.parquet"
MINE_SUMMARY = PROCESSED / "mine_related_stations_summary.csv"
FLOW_MATCHES = PROCESSED / "pbzn_nearest_flow_station_matches.csv"
DAILY_FLOW = PROCESSED / "nrfa_gdf_matched_daily_flow.csv"
BASELINE_STATIONS = PROCESSED / "pbzn_flow_station_summary.csv"
MANUAL_SAMPLES = PROCESSED / "pbzn_manual_flow_validation_samples.csv"
DEVIATING_RECORDS = PROCESSED / "raw_deviating_target_records.csv"

LOW_FLOW_PERCENTILE = 0.25


def percentile_of_score(reference: np.ndarray, values: np.ndarray) -> np.ndarray:
    ordered = np.sort(reference)
    return np.searchsorted(ordered, values, side="right") / len(ordered)


def load_station_date_pbzn() -> pd.DataFrame:
    mine_ids = set(
        pd.read_csv(MINE_SUMMARY, usecols=["station_id"])["station_id"].astype(str)
    )
    long = pd.read_parquet(
        LONG_PARQUET,
        columns=[
            "station_id",
            "station_name",
            "sample_date",
            "canonical_parameter",
            "value_standardised",
            "qualifier",
        ],
    )
    long["station_id"] = long["station_id"].astype(str)
    long = long[
        long["station_id"].isin(mine_ids)
        & long["canonical_parameter"].isin(["lead", "zinc"])
    ].copy()
    long["sample_date"] = pd.to_datetime(long["sample_date"])
    deviations = pd.read_csv(
        DEVIATING_RECORDS,
        usecols=["station_number", "sampling_datetime", "canonical_parameter"],
    ).rename(
        columns={
            "station_number": "station_id",
            "sampling_datetime": "sample_date",
        }
    )
    deviations["station_id"] = deviations["station_id"].astype(str)
    deviations["sample_date"] = pd.to_datetime(deviations["sample_date"])
    deviations = deviations.drop_duplicates(
        ["station_id", "sample_date", "canonical_parameter"]
    )
    long = long.merge(
        deviations.assign(_deviating=True),
        on=["station_id", "sample_date", "canonical_parameter"],
        how="left",
    )
    long = long[long["_deviating"].isna()].drop(columns="_deviating")
    qualifier = long["qualifier"].astype(str).str.strip()
    long["left_censored"] = qualifier.eq("<")
    long["right_censored"] = qualifier.eq(">")
    long["half_rl_value"] = np.where(
        long["left_censored"],
        pd.to_numeric(long["value_standardised"], errors="coerce") * 0.5,
        pd.to_numeric(long["value_standardised"], errors="coerce"),
    )

    grouped = (
        long.groupby(
            ["station_id", "station_name", "sample_date", "canonical_parameter"],
            dropna=False,
        )
        .agg(
            as_reported_value=("value_standardised", "mean"),
            half_rl_value=("half_rl_value", "mean"),
            any_left_censored=("left_censored", "max"),
            any_right_censored=("right_censored", "max"),
        )
        .reset_index()
    )

    keys = ["station_id", "station_name", "sample_date"]
    values = grouped.pivot(index=keys, columns="canonical_parameter", values="as_reported_value")
    half = grouped.pivot(index=keys, columns="canonical_parameter", values="half_rl_value")
    left = grouped.pivot(index=keys, columns="canonical_parameter", values="any_left_censored")
    right = grouped.pivot(index=keys, columns="canonical_parameter", values="any_right_censored")

    paired = values[["lead", "zinc"]].dropna().reset_index()
    paired["lead_half_rl"] = half.loc[values[["lead", "zinc"]].dropna().index, "lead"].to_numpy()
    paired["zinc_half_rl"] = half.loc[values[["lead", "zinc"]].dropna().index, "zinc"].to_numpy()
    paired["lead_censored"] = left.loc[values[["lead", "zinc"]].dropna().index, "lead"].fillna(False).to_numpy(bool)
    paired["zinc_censored"] = left.loc[values[["lead", "zinc"]].dropna().index, "zinc"].fillna(False).to_numpy(bool)
    paired["right_censored"] = (
        right.loc[values[["lead", "zinc"]].dropna().index, ["lead", "zinc"]]
        .fillna(False)
        .any(axis=1)
        .to_numpy(bool)
    )
    return paired[~paired["right_censored"]].copy()


def add_station_matches(paired: pd.DataFrame) -> pd.DataFrame:
    matches = pd.read_csv(FLOW_MATCHES)
    match_columns = [
        "station_id",
        "station_type",
        "wfd_c2_mgt_catchment_name",
        "nrfa_station_id",
        "nrfa_station_name",
        "nrfa_river",
        "flow_match_distance_km",
        "within_20km_flow_match",
    ]
    paired = paired.merge(matches[match_columns], on="station_id", how="inner")
    paired = paired[paired["within_20km_flow_match"].astype(bool)].copy()
    paired["sample_day"] = pd.to_datetime(paired["sample_date"]).dt.floor("D")
    return paired


def scenario_samples(paired: pd.DataFrame, scenario: str) -> pd.DataFrame:
    data = paired.copy()
    if scenario == "as_reported":
        data["lead_value"] = data["lead"]
        data["zinc_value"] = data["zinc"]
    elif scenario == "half_reporting_limit":
        data["lead_value"] = data["lead_half_rl"]
        data["zinc_value"] = data["zinc_half_rl"]
    elif scenario == "uncensored_only":
        data = data[~data["lead_censored"] & ~data["zinc_censored"]].copy()
        data["lead_value"] = data["lead"]
        data["zinc_value"] = data["zinc"]
    else:
        raise ValueError(scenario)

    data = data[(data["lead_value"] > 0) & (data["zinc_value"] > 0)].copy()
    data["pb_zn_ratio"] = data["lead_value"] / data["zinc_value"]
    lead_high = float(data["lead_value"].quantile(0.75))
    zinc_low = float(data["zinc_value"].quantile(0.25))
    ratio_high = float(data["pb_zn_ratio"].quantile(0.90))
    data["high_lead"] = data["lead_value"] >= lead_high
    data["low_zinc"] = data["zinc_value"] <= zinc_low
    data["high_pb_low_zinc"] = data["high_lead"] & data["low_zinc"]
    data["high_pb_zn_ratio"] = data["pb_zn_ratio"] >= ratio_high
    data.attrs["thresholds"] = {
        "lead_high_ug_l": lead_high,
        "zinc_low_ug_l": zinc_low,
        "high_pb_zn_ratio": ratio_high,
    }
    return data


def add_flow(data: pd.DataFrame, flows: pd.DataFrame) -> pd.DataFrame:
    merged = data.merge(
        flows[["nrfa_station_id", "flow_date", "flow_m3s"]],
        left_on=["nrfa_station_id", "sample_day"],
        right_on=["nrfa_station_id", "flow_date"],
        how="left",
    )
    merged["flow_percentile"] = np.nan
    for station_id, indices in merged.groupby("nrfa_station_id").groups.items():
        reference = flows.loc[
            flows["nrfa_station_id"].eq(station_id) & flows["flow_m3s"].ge(0),
            "flow_m3s",
        ].dropna().to_numpy(float)
        valid = merged.loc[indices, "flow_m3s"].notna()
        if len(reference) == 0 or not valid.any():
            continue
        valid_indices = valid[valid].index
        merged.loc[valid_indices, "flow_percentile"] = percentile_of_score(
            reference,
            merged.loc[valid_indices, "flow_m3s"].to_numpy(float),
        )
    merged["has_flow"] = merged["flow_percentile"].notna()
    merged["low_flow"] = merged["flow_percentile"] <= LOW_FLOW_PERCENTILE
    merged["low_flow_high_ratio"] = merged["low_flow"] & merged["high_pb_zn_ratio"]
    merged["low_flow_high_pb_low_zn"] = merged["low_flow"] & merged["high_pb_low_zinc"]
    return merged


def station_summary(data: pd.DataFrame, scenario: str) -> pd.DataFrame:
    rows = []
    group_columns = [
        "station_id",
        "station_name",
        "station_type",
        "wfd_c2_mgt_catchment_name",
        "nrfa_station_id",
        "nrfa_station_name",
        "flow_match_distance_km",
    ]
    for keys, group in data.groupby(group_columns, dropna=False):
        record = dict(zip(group_columns, keys, strict=False))
        with_flow = group[group["has_flow"]]
        n_with_flow = len(with_flow)
        n_ratio = int(with_flow["low_flow_high_ratio"].sum())
        n_strict = int(with_flow["low_flow_high_pb_low_zn"].sum())
        proportion = n_ratio / n_with_flow if n_with_flow else np.nan
        record.update(
            {
                "scenario": scenario,
                "n_pbzn": len(group),
                "n_with_flow": n_with_flow,
                "n_low_flow_high_pbzn": n_ratio,
                "n_low_flow_high_pb_low_zn": n_strict,
                "pct_low_flow_high_pbzn": proportion,
                "median_pb_zn_ratio": group["pb_zn_ratio"].median(),
            }
        )
        rows.append(record)

    summary = pd.DataFrame(rows)
    summary["systematic_candidate"] = (
        summary["n_with_flow"].ge(3)
        & (
            summary["n_low_flow_high_pb_low_zn"].ge(2)
            | summary["n_low_flow_high_pbzn"].ge(3)
            | (
                summary["pct_low_flow_high_pbzn"].ge(0.30)
                & summary["n_low_flow_high_pbzn"].ge(2)
            )
        )
    )
    return summary.sort_values(
        [
            "systematic_candidate",
            "n_low_flow_high_pb_low_zn",
            "n_low_flow_high_pbzn",
            "pct_low_flow_high_pbzn",
            "median_pb_zn_ratio",
        ],
        ascending=[False, False, False, False, False],
    )


def uncensored_manual_validation(
    uncensored_samples: pd.DataFrame,
    uncensored_automatic_stations: pd.DataFrame,
) -> pd.DataFrame:
    manual = pd.read_csv(MANUAL_SAMPLES, parse_dates=["sample_date"], low_memory=False)
    manual_columns = [
        "station_id",
        "sample_date",
        "selection_group",
        "manual_nrfa_id",
        "manual_nrfa_name",
        "manual_decision",
        "manual_flow_percentile",
    ]
    manual = manual[manual_columns].drop_duplicates(["station_id", "sample_date"])
    selected = uncensored_samples.merge(
        manual,
        on=["station_id", "sample_date"],
        how="inner",
    )
    selected["manual_has_flow"] = selected["manual_flow_percentile"].notna()
    selected["manual_low_flow"] = selected["manual_flow_percentile"] <= LOW_FLOW_PERCENTILE
    selected["manual_low_flow_high_ratio"] = (
        selected["manual_low_flow"] & selected["high_pb_zn_ratio"]
    )
    selected["manual_low_flow_high_pb_low_zn"] = (
        selected["manual_low_flow"] & selected["high_pb_low_zinc"]
    )

    rows = []
    for station_id, group in selected.groupby("station_id"):
        with_flow = group[group["manual_has_flow"]]
        n_with_flow = len(with_flow)
        n_ratio = int(with_flow["manual_low_flow_high_ratio"].sum())
        n_strict = int(with_flow["manual_low_flow_high_pb_low_zn"].sum())
        proportion = n_ratio / n_with_flow if n_with_flow else np.nan
        candidate = bool(
            n_with_flow >= 3
            and (
                n_strict >= 2
                or n_ratio >= 3
                or (proportion >= 0.30 and n_ratio >= 2)
            )
        )
        first = group.iloc[0]
        rows.append(
            {
                "station_id": station_id,
                "station_name": first["station_name"],
                "selection_group": first["selection_group"],
                "manual_nrfa_id": first["manual_nrfa_id"],
                "manual_nrfa_name": first["manual_nrfa_name"],
                "manual_decision": first["manual_decision"],
                "uncensored_n_samples": len(group),
                "manual_n_with_flow": n_with_flow,
                "manual_n_low_flow_high_pbzn": n_ratio,
                "manual_n_low_flow_high_pb_low_zn": n_strict,
                "manual_pct_low_flow_high_pbzn": proportion,
                "manual_systematic_candidate_uncensored": candidate,
            }
        )
    result = pd.DataFrame(rows)
    automatic = uncensored_automatic_stations[
        [
            "station_id",
            "n_with_flow",
            "n_low_flow_high_pbzn",
            "n_low_flow_high_pb_low_zn",
            "pct_low_flow_high_pbzn",
            "systematic_candidate",
        ]
    ].rename(
        columns={
            "n_with_flow": "automatic_n_with_flow",
            "n_low_flow_high_pbzn": "automatic_n_low_flow_high_pbzn",
            "n_low_flow_high_pb_low_zn": "automatic_n_low_flow_high_pb_low_zn",
            "pct_low_flow_high_pbzn": "automatic_pct_low_flow_high_pbzn",
            "systematic_candidate": "automatic_systematic_candidate_uncensored",
        }
    )
    result = result.merge(automatic, on="station_id", how="left")
    result["status"] = np.select(
        [
            result["manual_n_with_flow"].lt(3),
            result["automatic_systematic_candidate_uncensored"]
            & result["manual_systematic_candidate_uncensored"],
            result["automatic_systematic_candidate_uncensored"]
            & ~result["manual_systematic_candidate_uncensored"],
            ~result["automatic_systematic_candidate_uncensored"]
            & result["manual_systematic_candidate_uncensored"],
        ],
        [
            "Not evaluable",
            "Candidate retained",
            "Candidate lost",
            "New candidate",
        ],
        default="Not candidate in either",
    )
    return result.sort_values(
        ["automatic_systematic_candidate_uncensored", "manual_n_low_flow_high_pbzn"],
        ascending=[False, False],
    )


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    paired = add_station_matches(load_station_date_pbzn())
    flows = pd.read_csv(DAILY_FLOW, parse_dates=["flow_date"], low_memory=False)
    baseline_candidates = set(
        pd.read_csv(BASELINE_STATIONS)
        .query("systematic_candidate == True")["station_id"]
        .astype(str)
    )

    scenarios = ["as_reported", "half_reporting_limit", "uncensored_only"]
    metric_rows = []
    threshold_rows = []
    station_frames = []
    candidate_sets: dict[str, set[str]] = {}
    scenario_sample_frames: dict[str, pd.DataFrame] = {}
    scenario_flow_frames: dict[str, pd.DataFrame] = {}
    scenario_station_frames: dict[str, pd.DataFrame] = {}

    for scenario in scenarios:
        samples = scenario_samples(paired, scenario)
        thresholds = samples.attrs["thresholds"]
        with_flow = add_flow(samples, flows)
        stations = station_summary(with_flow, scenario)
        scenario_sample_frames[scenario] = samples
        scenario_flow_frames[scenario] = with_flow
        scenario_station_frames[scenario] = stations
        station_frames.append(stations)
        candidates = set(
            stations.loc[stations["systematic_candidate"], "station_id"].astype(str)
        )
        candidate_sets[scenario] = candidates

        exact_flow = with_flow[with_flow["has_flow"]]
        metric_rows.append(
            {
                "scenario": scenario,
                "n_pbzn_samples": len(samples),
                "n_pbzn_stations": samples["station_id"].nunique(),
                "n_same_day_flow": int(with_flow["has_flow"].sum()),
                "spearman_pb_zn": samples[["lead_value", "zinc_value"]]
                .corr(method="spearman")
                .iloc[0, 1],
                "spearman_ratio_flow": exact_flow[["pb_zn_ratio", "flow_percentile"]]
                .corr(method="spearman")
                .iloc[0, 1],
                "median_pb_zn_ratio": samples["pb_zn_ratio"].median(),
                "n_low_flow_high_ratio": int(with_flow["low_flow_high_ratio"].sum()),
                "n_low_flow_high_pb_low_zn": int(
                    with_flow["low_flow_high_pb_low_zn"].sum()
                ),
                "n_candidates": len(candidates),
                "baseline_candidates_retained": len(candidates & baseline_candidates),
                "new_candidates_vs_baseline": len(candidates - baseline_candidates),
            }
        )
        threshold_rows.append({"scenario": scenario, **thresholds})

    baseline = candidate_sets["as_reported"]
    for row in metric_rows:
        scenario_set = candidate_sets[row["scenario"]]
        union = baseline | scenario_set
        row["candidate_jaccard_vs_as_reported"] = (
            len(baseline & scenario_set) / len(union) if union else 1.0
        )

    metrics = pd.DataFrame(metric_rows)
    thresholds = pd.DataFrame(threshold_rows)
    stations_all = pd.concat(station_frames, ignore_index=True)
    metrics.to_csv(RESULTS / "7.5_Censoring_Metrics.csv", index=False)
    thresholds.to_csv(RESULTS / "7.5_Censoring_Thresholds.csv", index=False)
    stations_all.to_csv(RESULTS / "7.5_Censoring_Station_Sensitivity.csv", index=False)
    scenario_flow_frames["uncensored_only"].to_csv(
        RESULTS / "7.5_Uncensored_PbZn_Flow_Samples.csv",
        index=False,
    )
    manual_uncensored = uncensored_manual_validation(
        scenario_sample_frames["uncensored_only"],
        scenario_station_frames["uncensored_only"],
    )
    manual_uncensored.to_csv(
        RESULTS / "7.5_Uncensored_Manual_Validation.csv",
        index=False,
    )

    with pd.ExcelWriter(RESULTS / "7.5_Censoring_Sensitivity.xlsx", engine="openpyxl") as writer:
        metrics.to_excel(writer, index=False, sheet_name="metrics")
        thresholds.to_excel(writer, index=False, sheet_name="thresholds")
        for scenario in scenarios:
            stations_all[stations_all["scenario"].eq(scenario)].to_excel(
                writer,
                index=False,
                sheet_name=scenario[:31],
            )
        manual_uncensored.to_excel(
            writer,
            index=False,
            sheet_name="uncensored_manual",
        )

    plot = metrics.copy()
    labels = {
        "as_reported": "Reporting limit\nas value",
        "half_reporting_limit": "Half reporting\nlimit",
        "uncensored_only": "Uncensored\npairs only",
    }
    plot["label"] = plot["scenario"].map(labels)
    fig, axes = plt.subplots(1, 2, figsize=(11, 5), constrained_layout=True)
    sns.barplot(data=plot, x="label", y="n_pbzn_samples", color="#4D7895", ax=axes[0])
    axes[0].set_title("Paired Pb/Zn samples")
    axes[0].set_xlabel("")
    axes[0].set_ylabel("Samples")
    sns.barplot(data=plot, x="label", y="n_candidates", color="#B45A45", ax=axes[1])
    axes[1].set_title("Systematic candidate stations")
    axes[1].set_xlabel("")
    axes[1].set_ylabel("Stations")
    fig.savefig(RESULTS / "7.5_Censoring_Sensitivity.png", dpi=220)
    plt.close(fig)

    print(metrics.to_string(index=False))
    print(thresholds.to_string(index=False))
    robust = manual_uncensored[
        manual_uncensored["automatic_systematic_candidate_uncensored"].fillna(False)
    ]
    print("Uncensored automatic candidates after manual rematching:")
    print(robust["status"].value_counts(dropna=False).to_string())
    print(f"Wrote outputs to {RESULTS}")


if __name__ == "__main__":
    main()
