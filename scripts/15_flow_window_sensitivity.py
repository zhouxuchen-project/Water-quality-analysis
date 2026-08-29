from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
RESULTS = ROOT / "results" / "7.5_sensitivity"

SAMPLES = RESULTS / "7.5_Uncensored_PbZn_Flow_Samples.csv"
DAILY_FLOW = PROCESSED / "nrfa_gdf_matched_daily_flow.csv"
LOW_FLOW_PERCENTILE = 0.25


def percentile_of_score(reference: np.ndarray, values: np.ndarray) -> np.ndarray:
    ordered = np.sort(reference)
    return np.searchsorted(ordered, values, side="right") / len(ordered)


def rolling_flow_table(flows: pd.DataFrame, window: int) -> pd.DataFrame:
    frames = []
    for station_id, group in flows.groupby("nrfa_station_id"):
        group = group.sort_values("flow_date").drop_duplicates("flow_date", keep="last")
        calendar = group.set_index("flow_date")[["flow_m3s"]].asfreq("D")
        rolling = calendar["flow_m3s"].rolling(window, min_periods=window).mean()
        reference = rolling.dropna().to_numpy(float)
        table = rolling.rename("window_flow_m3s").reset_index()
        table["nrfa_station_id"] = station_id
        table["window_flow_percentile"] = np.nan
        valid = table["window_flow_m3s"].notna()
        if len(reference) and valid.any():
            table.loc[valid, "window_flow_percentile"] = percentile_of_score(
                reference,
                table.loc[valid, "window_flow_m3s"].to_numpy(float),
            )
        frames.append(table)
    return pd.concat(frames, ignore_index=True)


def station_summary(samples: pd.DataFrame, method: str) -> pd.DataFrame:
    rows = []
    for (station_id, station_name), group in samples.groupby(
        ["station_id", "station_name"], dropna=False
    ):
        with_flow = group[group["window_flow_percentile"].notna()]
        n_with_flow = len(with_flow)
        n_ratio = int(with_flow["low_flow_high_ratio_window"].sum())
        n_strict = int(with_flow["low_flow_high_pb_low_zn_window"].sum())
        proportion = n_ratio / n_with_flow if n_with_flow else np.nan
        candidate = bool(
            n_with_flow >= 3
            and (
                n_strict >= 2
                or n_ratio >= 3
                or (proportion >= 0.30 and n_ratio >= 2)
            )
        )
        rows.append(
            {
                "method": method,
                "station_id": station_id,
                "station_name": station_name,
                "n_with_flow": n_with_flow,
                "n_low_flow_high_pbzn": n_ratio,
                "n_low_flow_high_pb_low_zn": n_strict,
                "pct_low_flow_high_pbzn": proportion,
                "systematic_candidate": candidate,
            }
        )
    return pd.DataFrame(rows)


def add_window(samples: pd.DataFrame, flows: pd.DataFrame, window: int) -> pd.DataFrame:
    if window == 1:
        result = samples.copy()
        result["window_flow_m3s"] = result["flow_m3s"]
        result["window_flow_percentile"] = result["flow_percentile"]
    else:
        rolling = rolling_flow_table(flows, window)
        result = samples.drop(
            columns=["window_flow_m3s", "window_flow_percentile"],
            errors="ignore",
        ).merge(
            rolling,
            left_on=["nrfa_station_id", "sample_day"],
            right_on=["nrfa_station_id", "flow_date"],
            how="left",
        )
    result["low_flow_window"] = result["window_flow_percentile"] <= LOW_FLOW_PERCENTILE
    result["low_flow_high_ratio_window"] = (
        result["low_flow_window"] & result["high_pb_zn_ratio"].astype(bool)
    )
    result["low_flow_high_pb_low_zn_window"] = (
        result["low_flow_window"] & result["high_pb_low_zinc"].astype(bool)
    )
    return result


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    samples = pd.read_csv(SAMPLES, parse_dates=["sample_day"], low_memory=False)
    flows = pd.read_csv(DAILY_FLOW, parse_dates=["flow_date"], low_memory=False)
    flows["flow_m3s"] = pd.to_numeric(flows["flow_m3s"], errors="coerce")
    flows = flows[flows["flow_m3s"].ge(0)].copy()

    methods = {1: "same_day", 3: "antecedent_3_day_mean", 7: "antecedent_7_day_mean"}
    sample_frames: dict[str, pd.DataFrame] = {}
    station_frames = []
    metric_rows = []
    candidate_sets: dict[str, set[str]] = {}

    for window, method in methods.items():
        method_samples = add_window(samples, flows, window)
        method_stations = station_summary(method_samples, method)
        sample_frames[method] = method_samples
        station_frames.append(method_stations)
        candidate_set = set(
            method_stations.loc[
                method_stations["systematic_candidate"], "station_id"
            ].astype(str)
        )
        candidate_sets[method] = candidate_set
        with_flow = method_samples[method_samples["window_flow_percentile"].notna()]
        metric_rows.append(
            {
                "method": method,
                "window_days": window,
                "n_with_flow": len(with_flow),
                "spearman_ratio_flow": with_flow[
                    ["pb_zn_ratio", "window_flow_percentile"]
                ]
                .corr(method="spearman")
                .iloc[0, 1],
                "n_low_flow_high_ratio": int(
                    with_flow["low_flow_high_ratio_window"].sum()
                ),
                "n_low_flow_high_pb_low_zn": int(
                    with_flow["low_flow_high_pb_low_zn_window"].sum()
                ),
                "n_candidates": len(candidate_set),
            }
        )

    baseline = sample_frames["same_day"]
    baseline_candidates = candidate_sets["same_day"]
    for row in metric_rows:
        method = row["method"]
        current = sample_frames[method]
        both = baseline["window_flow_percentile"].notna() & current[
            "window_flow_percentile"
        ].notna()
        row["n_comparable_to_same_day"] = int(both.sum())
        changed = (
            baseline.loc[both, "low_flow_window"].astype(bool).to_numpy()
            != current.loc[both, "low_flow_window"].astype(bool).to_numpy()
        )
        row["n_low_flow_class_changes"] = int(changed.sum())
        row["low_flow_class_change_rate"] = float(changed.mean()) if len(changed) else np.nan
        current_candidates = candidate_sets[method]
        union = baseline_candidates | current_candidates
        row["baseline_candidates_retained"] = len(
            baseline_candidates & current_candidates
        )
        row["candidate_jaccard_vs_same_day"] = (
            len(baseline_candidates & current_candidates) / len(union) if union else 1.0
        )

    metrics = pd.DataFrame(metric_rows)
    station_results = pd.concat(station_frames, ignore_index=True)
    metrics.to_csv(RESULTS / "7.5_Flow_Window_Metrics.csv", index=False)
    station_results.to_csv(RESULTS / "7.5_Flow_Window_Stations.csv", index=False)

    with pd.ExcelWriter(RESULTS / "7.5_Flow_Window_Sensitivity.xlsx", engine="openpyxl") as writer:
        metrics.to_excel(writer, index=False, sheet_name="metrics")
        station_results.to_excel(writer, index=False, sheet_name="stations")

    plot = metrics.copy()
    plot["label"] = plot["window_days"].map(
        {1: "Same day", 3: "Previous 3 days", 7: "Previous 7 days"}
    )
    fig, axes = plt.subplots(1, 2, figsize=(11, 5), constrained_layout=True)
    sns.barplot(data=plot, x="label", y="n_low_flow_high_ratio", color="#4D7895", ax=axes[0])
    axes[0].set_title("Low-flow, high-Pb/Zn events")
    axes[0].set_xlabel("")
    axes[0].set_ylabel("Events")
    sns.barplot(data=plot, x="label", y="n_candidates", color="#B45A45", ax=axes[1])
    axes[1].set_title("Systematic candidate stations")
    axes[1].set_xlabel("")
    axes[1].set_ylabel("Stations")
    fig.savefig(RESULTS / "7.5_Flow_Window_Sensitivity.png", dpi=220)
    plt.close(fig)

    print(metrics.to_string(index=False))
    print(f"Wrote outputs to {RESULTS}")


if __name__ == "__main__":
    main()
