from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import sleep
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import seaborn as sns


ROOT = Path(__file__).resolve().parents[1]
RAW_FLOW = ROOT / "data" / "raw" / "river_flow"
PROCESSED = ROOT / "data" / "processed"
FIGURES = ROOT / "figures"
RESULTS = ROOT / "results" / "7.3_pbzn_flow"

MINE_WIDE = PROCESSED / "mine_related_stations_wide.csv"

NRFA_BASE = "https://nrfaapps.ceh.ac.uk/nrfa/ws"
NRFA_STATION_INFO_URL = (
    f"{NRFA_BASE}/station-info"
    "?station=*&format=json-object&fields=station-information,gdf-statistics,category"
)

LOW_FLOW_PERCENTILE = 0.25
VERY_LOW_FLOW_PERCENTILE = 0.10
FLOW_MATCH_DISTANCE_KM = 20.0


@dataclass(frozen=True)
class Thresholds:
    lead_high_ug_l: float
    zinc_low_ug_l: float
    pb_zn_high_ratio: float
    low_flow_percentile: float = LOW_FLOW_PERCENTILE
    very_low_flow_percentile: float = VERY_LOW_FLOW_PERCENTILE


def ensure_dirs() -> None:
    for path in [RAW_FLOW, PROCESSED, FIGURES, RESULTS]:
        path.mkdir(parents=True, exist_ok=True)


def get_json(url: str, timeout: int = 60, attempts: int = 3) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # pragma: no cover - network retry guard
            last_error = exc
            if attempt < attempts:
                sleep(1.5 * attempt)
    raise RuntimeError(f"Could not fetch {url}") from last_error


def flatten_nrfa_station_metadata(records: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in records:
        rows.append(
            {
                "nrfa_station_id": item.get("id"),
                "nrfa_station_name": item.get("name"),
                "river": item.get("river"),
                "location": item.get("location"),
                "measuring_authority_id": item.get("measuring-authority-id"),
                "measuring_authority_station_id": item.get("measuring-authority-station-id"),
                "hydrometric_area": item.get("hydrometric-area"),
                "station_type": item.get("station-type"),
                "easting": item.get("easting"),
                "northing": item.get("northing"),
                "latitude": item.get("latitude"),
                "longitude": item.get("longitude"),
                "opened": item.get("opened"),
                "closed": item.get("closed"),
                "gdf_start_date": item.get("gdf-start-date"),
                "gdf_end_date": item.get("gdf-end-date"),
                "gdf_mean_flow_m3s": item.get("gdf-mean-flow"),
                "gdf_min_flow_m3s": item.get("gdf-min-flow"),
                "gdf_q95_flow_m3s": item.get("gdf-q95-flow"),
                "gdf_q70_flow_m3s": item.get("gdf-q70-flow"),
                "gdf_q50_flow_m3s": item.get("gdf-q50-flow"),
                "gdf_q10_flow_m3s": item.get("gdf-q10-flow"),
                "gdf_q05_flow_m3s": item.get("gdf-q05-flow"),
                "gdf_percent_complete": item.get("gdf-percent-complete"),
                "nrfa_mean_flow": item.get("nrfa-mean-flow"),
                "live_data": item.get("live-data"),
            }
        )
    return pd.DataFrame(rows)


def download_nrfa_station_metadata() -> tuple[pd.DataFrame, pd.DataFrame]:
    payload = get_json(NRFA_STATION_INFO_URL)
    all_stations = flatten_nrfa_station_metadata(payload["data"])
    all_stations.to_csv(RAW_FLOW / "nrfa_station_metadata_all.csv", index=False)

    nrw_flow = all_stations[
        (all_stations["measuring_authority_id"] == "NRW")
        & (all_stations["nrfa_mean_flow"] == True)  # noqa: E712
        & all_stations["easting"].notna()
        & all_stations["northing"].notna()
    ].copy()
    nrw_flow.to_csv(RAW_FLOW / "nrfa_nrw_flow_stations.csv", index=False)
    return all_stations, nrw_flow


def load_pbzn_samples() -> tuple[pd.DataFrame, Thresholds]:
    mine = pd.read_csv(MINE_WIDE, parse_dates=["sample_date"], low_memory=False)
    samples = mine.dropna(subset=["lead", "zinc", "easting", "northing"]).copy()
    samples = samples[(samples["lead"] > 0) & (samples["zinc"] > 0)].copy()
    samples["sample_day"] = samples["sample_date"].dt.floor("D")
    samples["pb_zn_ratio"] = samples["lead"] / samples["zinc"]

    thresholds = Thresholds(
        lead_high_ug_l=float(samples["lead"].quantile(0.75)),
        zinc_low_ug_l=float(samples["zinc"].quantile(0.25)),
        pb_zn_high_ratio=float(samples["pb_zn_ratio"].quantile(0.90)),
    )
    samples["high_lead"] = samples["lead"] >= thresholds.lead_high_ug_l
    samples["low_zinc"] = samples["zinc"] <= thresholds.zinc_low_ug_l
    samples["high_pb_low_zinc"] = samples["high_lead"] & samples["low_zinc"]
    samples["high_pb_zn_ratio"] = samples["pb_zn_ratio"] >= thresholds.pb_zn_high_ratio
    return samples, thresholds


def match_water_stations_to_flow(samples: pd.DataFrame, flow_stations: pd.DataFrame) -> pd.DataFrame:
    water_stations = (
        samples[
            [
                "station_id",
                "station_name",
                "easting",
                "northing",
                "wfd_c2_mgt_catchment_name",
                "station_type",
            ]
        ]
        .drop_duplicates("station_id")
        .reset_index(drop=True)
        .copy()
    )
    flow = flow_stations.reset_index(drop=True).copy()
    water_xy = water_stations[["easting", "northing"]].to_numpy(float)
    flow_xy = flow[["easting", "northing"]].to_numpy(float)
    distances = np.sqrt(((water_xy[:, None, :] - flow_xy[None, :, :]) ** 2).sum(axis=2))
    nearest_index = distances.argmin(axis=1)

    nearest = flow.iloc[nearest_index].reset_index(drop=True)
    water_stations["nrfa_station_id"] = nearest["nrfa_station_id"].to_numpy()
    water_stations["nrfa_station_name"] = nearest["nrfa_station_name"].to_numpy()
    water_stations["nrfa_river"] = nearest["river"].to_numpy()
    water_stations["nrfa_location"] = nearest["location"].to_numpy()
    water_stations["nrfa_gdf_start_date"] = nearest["gdf_start_date"].to_numpy()
    water_stations["nrfa_gdf_end_date"] = nearest["gdf_end_date"].to_numpy()
    water_stations["nrfa_gdf_mean_flow_m3s"] = nearest["gdf_mean_flow_m3s"].to_numpy()
    water_stations["flow_match_distance_km"] = distances.min(axis=1) / 1000
    water_stations["within_20km_flow_match"] = (
        water_stations["flow_match_distance_km"] <= FLOW_MATCH_DISTANCE_KM
    )
    water_stations.to_csv(PROCESSED / "pbzn_nearest_flow_station_matches.csv", index=False)
    return water_stations


def parse_nrfa_stream(payload: dict[str, Any]) -> pd.DataFrame:
    station = payload["station"]
    data_type = payload["data-type"]
    stream = payload.get("data-stream", [])
    rows: list[dict[str, Any]] = []
    current_date: pd.Timestamp | None = None

    for item in stream:
        if isinstance(item, str):
            current_date = pd.to_datetime(item)
            continue
        if current_date is None:
            continue
        if isinstance(item, list):
            value = item[0]
            flag = item[1] if len(item) > 1 else ""
        else:
            value = item
            flag = ""
        rows.append(
            {
                "nrfa_station_id": station.get("id"),
                "nrfa_station_name": station.get("name"),
                "flow_date": current_date.floor("D"),
                "flow_m3s": value,
                "flow_flag": flag,
                "flow_units": data_type.get("units", "m3/s"),
            }
        )
        current_date = current_date + pd.Timedelta(days=1)
    return pd.DataFrame(rows)


def download_daily_flows(nrfa_station_ids: list[int]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for station_id in sorted(set(int(x) for x in nrfa_station_ids)):
        raw_path = RAW_FLOW / f"nrfa_gdf_{station_id}.json"
        if raw_path.exists():
            payload = pd.read_json(raw_path, typ="series").to_dict()
        else:
            url = (
                f"{NRFA_BASE}/time-series"
                f"?format=json-object&data-type=gdf&station={station_id}&flags=true&dates=true"
            )
            payload = get_json(url, timeout=90)
            raw_path.write_text(pd.Series(payload).to_json(force_ascii=False), encoding="utf-8")
        frame = parse_nrfa_stream(payload)
        if not frame.empty:
            frames.append(frame)
    flows = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    flows["flow_m3s"] = pd.to_numeric(flows["flow_m3s"], errors="coerce")
    flows = flows.dropna(subset=["flow_m3s"])
    flows.to_csv(PROCESSED / "nrfa_gdf_matched_daily_flow.csv", index=False)
    return flows


def add_flow_percentiles(samples: pd.DataFrame, flows: pd.DataFrame) -> pd.DataFrame:
    merged = samples.merge(
        flows[["nrfa_station_id", "flow_date", "flow_m3s", "flow_flag"]],
        left_on=["nrfa_station_id", "sample_day"],
        right_on=["nrfa_station_id", "flow_date"],
        how="left",
    )
    merged["flow_percentile"] = np.nan
    merged["flow_p10_m3s"] = np.nan
    merged["flow_p25_m3s"] = np.nan
    merged["flow_p50_m3s"] = np.nan

    for station_id, idx in merged.groupby("nrfa_station_id").groups.items():
        station_flows = flows.loc[flows["nrfa_station_id"] == station_id, "flow_m3s"].dropna()
        station_flows = station_flows[station_flows >= 0].to_numpy()
        if len(station_flows) == 0:
            continue
        sorted_flows = np.sort(station_flows)
        sample_values = merged.loc[idx, "flow_m3s"].to_numpy()
        valid = ~np.isnan(sample_values)
        percentiles = np.full(len(sample_values), np.nan)
        percentiles[valid] = np.searchsorted(sorted_flows, sample_values[valid], side="right") / len(
            sorted_flows
        )
        merged.loc[idx, "flow_percentile"] = percentiles
        merged.loc[idx, "flow_p10_m3s"] = np.quantile(station_flows, 0.10)
        merged.loc[idx, "flow_p25_m3s"] = np.quantile(station_flows, 0.25)
        merged.loc[idx, "flow_p50_m3s"] = np.quantile(station_flows, 0.50)

    merged["has_flow_match"] = merged["flow_m3s"].notna()
    merged["low_flow"] = merged["flow_percentile"] <= LOW_FLOW_PERCENTILE
    merged["very_low_flow"] = merged["flow_percentile"] <= VERY_LOW_FLOW_PERCENTILE
    merged["low_flow_high_pb_low_zinc"] = merged["low_flow"] & merged["high_pb_low_zinc"]
    merged["low_flow_high_pb_zn_ratio"] = merged["low_flow"] & merged["high_pb_zn_ratio"]
    merged["very_low_flow_high_pb_zn_ratio"] = merged["very_low_flow"] & merged["high_pb_zn_ratio"]

    conditions = [
        merged["flow_percentile"].isna(),
        merged["flow_percentile"] <= VERY_LOW_FLOW_PERCENTILE,
        merged["flow_percentile"] <= LOW_FLOW_PERCENTILE,
    ]
    choices = ["missing_flow", "very_low_flow", "low_flow"]
    merged["flow_class"] = np.select(conditions, choices, default="normal_or_high_flow")
    return merged


def station_summary(merged: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    group_cols = [
        "station_id",
        "station_name",
        "station_type",
        "wfd_c2_mgt_catchment_name",
        "nrfa_station_id",
        "nrfa_station_name",
        "nrfa_river",
        "flow_match_distance_km",
    ]
    for keys, group in merged.groupby(group_cols, dropna=False):
        record = dict(zip(group_cols, keys, strict=False))
        with_flow = group[group["has_flow_match"]].copy()
        n_with_flow = len(with_flow)
        n_pbzn = len(group)
        n_low_flow_high_ratio = int(with_flow["low_flow_high_pb_zn_ratio"].sum())
        n_low_flow_high_pb_low_zn = int(with_flow["low_flow_high_pb_low_zinc"].sum())
        record.update(
            {
                "n_pbzn_samples": n_pbzn,
                "n_with_flow": n_with_flow,
                "n_low_flow_samples": int(with_flow["low_flow"].sum()) if n_with_flow else 0,
                "n_high_pb_low_zinc": int(group["high_pb_low_zinc"].sum()),
                "n_high_pbzn_ratio": int(group["high_pb_zn_ratio"].sum()),
                "n_low_flow_high_pbzn_ratio": n_low_flow_high_ratio,
                "n_low_flow_high_pb_low_zinc": n_low_flow_high_pb_low_zn,
                "pct_low_flow_high_pbzn_ratio": (
                    n_low_flow_high_ratio / n_with_flow if n_with_flow else np.nan
                ),
                "pct_low_flow_high_pb_low_zinc": (
                    n_low_flow_high_pb_low_zn / n_with_flow if n_with_flow else np.nan
                ),
                "median_lead_ug_l": group["lead"].median(),
                "median_zinc_ug_l": group["zinc"].median(),
                "median_pb_zn_ratio": group["pb_zn_ratio"].median(),
                "max_pb_zn_ratio": group["pb_zn_ratio"].max(),
                "median_flow_percentile": with_flow["flow_percentile"].median()
                if n_with_flow
                else np.nan,
            }
        )
        rows.append(record)

    summary = pd.DataFrame(rows)
    summary["systematic_candidate"] = (
        (summary["n_with_flow"] >= 3)
        & (
            (summary["n_low_flow_high_pb_low_zinc"] >= 2)
            | (summary["n_low_flow_high_pbzn_ratio"] >= 3)
            | (
                (summary["pct_low_flow_high_pbzn_ratio"] >= 0.30)
                & (summary["n_low_flow_high_pbzn_ratio"] >= 2)
            )
        )
    )
    sort_cols = [
        "systematic_candidate",
        "n_low_flow_high_pb_low_zinc",
        "n_low_flow_high_pbzn_ratio",
        "pct_low_flow_high_pbzn_ratio",
        "median_pb_zn_ratio",
    ]
    return summary.sort_values(sort_cols, ascending=[False, False, False, False, False])


def write_thresholds(thresholds: Thresholds, samples: pd.DataFrame, merged: pd.DataFrame) -> pd.DataFrame:
    rows = [
        {
            "threshold": "high_lead",
            "definition": "lead >= 75th percentile of mine-related Pb/Zn paired samples",
            "value": thresholds.lead_high_ug_l,
            "unit": "ug/L",
        },
        {
            "threshold": "low_zinc",
            "definition": "zinc <= 25th percentile of mine-related Pb/Zn paired samples",
            "value": thresholds.zinc_low_ug_l,
            "unit": "ug/L",
        },
        {
            "threshold": "high_pb_zn_ratio",
            "definition": "Pb/Zn >= 90th percentile of mine-related Pb/Zn paired samples",
            "value": thresholds.pb_zn_high_ratio,
            "unit": "unitless because Pb and Zn are both ug/L",
        },
        {
            "threshold": "low_flow",
            "definition": "daily flow percentile <= 25th percentile for matched NRFA station",
            "value": thresholds.low_flow_percentile,
            "unit": "station-specific flow percentile",
        },
        {
            "threshold": "very_low_flow",
            "definition": "daily flow percentile <= 10th percentile for matched NRFA station",
            "value": thresholds.very_low_flow_percentile,
            "unit": "station-specific flow percentile",
        },
        {
            "threshold": "flow_match_distance",
            "definition": "nearest NRW NRFA gauging station accepted for first-pass matching",
            "value": FLOW_MATCH_DISTANCE_KM,
            "unit": "km",
        },
        {
            "threshold": "pbzn_sample_count",
            "definition": "mine-related records with both positive lead and positive zinc",
            "value": len(samples),
            "unit": "station-date samples",
        },
        {
            "threshold": "pbzn_flow_matched_count",
            "definition": "Pb/Zn station-date samples with same-day NRFA daily flow",
            "value": int(merged["has_flow_match"].sum()),
            "unit": "station-date samples",
        },
    ]
    table = pd.DataFrame(rows)
    table.to_csv(PROCESSED / "pbzn_flow_thresholds.csv", index=False)
    return table


def plot_ratio_vs_flow(merged: pd.DataFrame) -> None:
    data = merged[merged["has_flow_match"]].copy()
    if data.empty:
        return
    plot_data = data.copy()
    if len(plot_data) > 10000:
        plot_data = plot_data.sample(10000, random_state=42)
    plot_data["case_type"] = np.where(
        plot_data["low_flow_high_pb_low_zinc"],
        "Low flow + high Pb/low Zn",
        "Other sample",
    )

    plt.figure(figsize=(9, 6))
    ax = sns.scatterplot(
        data=plot_data,
        x="flow_percentile",
        y="pb_zn_ratio",
        hue="case_type",
        hue_order=["Other sample", "Low flow + high Pb/low Zn"],
        palette={"Other sample": "#5176a3", "Low flow + high Pb/low Zn": "#c43f3f"},
        alpha=0.55,
        s=22,
        linewidth=0,
    )
    plt.yscale("log")
    plt.axvline(LOW_FLOW_PERCENTILE, color="#222222", linestyle="--", linewidth=1)
    plt.xlabel("Matched NRFA flow percentile on sampling day")
    plt.ylabel("Pb/Zn ratio, log scale")
    plt.title("Pb/Zn ratio under matched daily river flow")
    ax.legend(title="")
    plt.tight_layout()
    plt.savefig(FIGURES / "pbzn_ratio_vs_flow.png", dpi=220)
    plt.close()


def plot_ratio_by_flow_class(merged: pd.DataFrame) -> None:
    data = merged[merged["has_flow_match"]].copy()
    if data.empty:
        return
    label_map = {
        "very_low_flow": "Very low flow\n(<=10th pct.)",
        "low_flow": "Low flow\n(10th-25th pct.)",
        "normal_or_high_flow": "Normal/high flow\n(>25th pct.)",
    }
    data["flow_class_label"] = data["flow_class"].map(label_map)
    order = [label_map["very_low_flow"], label_map["low_flow"], label_map["normal_or_high_flow"]]
    plt.figure(figsize=(8, 6))
    sns.boxplot(
        data=data,
        x="flow_class_label",
        y="pb_zn_ratio",
        order=order,
        color="#86b6a5",
        showfliers=False,
    )
    plt.yscale("log")
    plt.xlabel("")
    plt.ylabel("Pb/Zn ratio, log scale")
    plt.title("Pb/Zn ratio by flow class")
    plt.tight_layout()
    plt.savefig(FIGURES / "pbzn_ratio_by_flow_class.png", dpi=220)
    plt.close()


def plot_lead_zinc_flow_quadrants(merged: pd.DataFrame, thresholds: Thresholds) -> None:
    data = merged[merged["has_flow_match"]].copy()
    if data.empty:
        return
    if len(data) > 10000:
        data = data.sample(10000, random_state=42)
    label_map = {
        "very_low_flow": "Very low flow",
        "low_flow": "Low flow",
        "normal_or_high_flow": "Normal/high flow",
    }
    data["flow_class_label"] = data["flow_class"].map(label_map)
    plt.figure(figsize=(8, 7))
    ax = sns.scatterplot(
        data=data,
        x="zinc",
        y="lead",
        hue="flow_class_label",
        hue_order=["Very low flow", "Low flow", "Normal/high flow"],
        palette={
            "Very low flow": "#c43f3f",
            "Low flow": "#e19a3b",
            "Normal/high flow": "#5176a3",
        },
        alpha=0.55,
        s=20,
        linewidth=0,
    )
    plt.xscale("log")
    plt.yscale("log")
    plt.axhline(thresholds.lead_high_ug_l, color="#222222", linestyle="--", linewidth=1)
    plt.axvline(thresholds.zinc_low_ug_l, color="#222222", linestyle="--", linewidth=1)
    plt.xlabel("Zinc (ug/L), log scale")
    plt.ylabel("Lead (ug/L), log scale")
    plt.title("High Pb / low Zn quadrant by flow class")
    ax.legend(title="")
    plt.tight_layout()
    plt.savefig(FIGURES / "pbzn_lead_zinc_flow_quadrants.png", dpi=220)
    plt.close()


def plot_systematic_sites(summary: pd.DataFrame) -> None:
    data = summary[summary["n_with_flow"] >= 3].copy()
    if data.empty:
        return
    data = data.sort_values("n_low_flow_high_pbzn_ratio", ascending=False).head(15)
    plt.figure(figsize=(10, 7))
    sns.barplot(data=data, y="station_name", x="n_low_flow_high_pbzn_ratio", color="#b55a4a")
    plt.xlabel("Low-flow samples with high Pb/Zn ratio")
    plt.ylabel("")
    plt.title("Stations with repeated low-flow high Pb/Zn behaviour")
    plt.tight_layout()
    plt.savefig(FIGURES / "pbzn_low_flow_systematic_sites.png", dpi=220)
    plt.close()


def write_excel_exports(
    merged: pd.DataFrame,
    summary: pd.DataFrame,
    matches: pd.DataFrame,
    thresholds: pd.DataFrame,
) -> None:
    exports = [
        (merged, RESULTS / "7.3_PbZn_Flow_Samples.xlsx"),
        (summary, RESULTS / "7.3_Systematic_Sites.xlsx"),
        (matches, RESULTS / "7.3_Flow_Station_Matches.xlsx"),
        (thresholds, RESULTS / "7.3_Thresholds.xlsx"),
    ]
    for frame, path in exports:
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            frame.to_excel(writer, index=False, sheet_name="data")
            ws = writer.book["data"]
            ws.freeze_panes = "A2"
            for cell in ws[1]:
                cell.style = "Headline 4"
            for col in ws.columns:
                max_len = min(max(len(str(c.value)) if c.value is not None else 0 for c in col), 48)
                ws.column_dimensions[col[0].column_letter].width = max(12, max_len + 2)


def copy_figures_to_results() -> None:
    mapping = {
        "pbzn_ratio_vs_flow.png": "7.3_Ratio_vs_Flow.png",
        "pbzn_ratio_by_flow_class.png": "7.3_Ratio_By_Flow_Class.png",
        "pbzn_lead_zinc_flow_quadrants.png": "7.3_HighPb_LowZn_Flow.png",
        "pbzn_low_flow_systematic_sites.png": "7.3_Systematic_Sites.png",
    }
    for src_name, dest_name in mapping.items():
        src = FIGURES / src_name
        if src.exists():
            (RESULTS / dest_name).write_bytes(src.read_bytes())


def make_summary_docx(merged: pd.DataFrame, summary: pd.DataFrame, thresholds: Thresholds) -> None:
    from zipfile import ZIP_DEFLATED, ZipFile
    from xml.sax.saxutils import escape

    path = RESULTS / "summary.docx"
    n_pbzn = len(merged)
    n_flow = int(merged["has_flow_match"].sum())
    n_low_flow_high_ratio = int(merged["low_flow_high_pb_zn_ratio"].sum())
    n_low_flow_high_pb_low_zn = int(merged["low_flow_high_pb_low_zinc"].sum())
    n_candidates = int(summary["systematic_candidate"].sum())
    top = summary.head(5)[
        [
            "station_name",
            "n_with_flow",
            "n_low_flow_high_pbzn_ratio",
            "n_low_flow_high_pb_low_zinc",
            "median_pb_zn_ratio",
        ]
    ]

    lines = [
        "Summary: Pb/Zn and River Flow Analysis",
        "Date prepared: 2026-07-02",
        "",
        "Purpose",
        "This analysis responds to the supervisor's request to focus on the Pb/Zn ratio and look for systematic low-flow situations with high lead and low zinc.",
        "",
        "Data source",
        "River flow data were retrieved from the UK National River Flow Archive (NRFA) API as gauged daily mean flow in m3/s. Water quality stations were matched to the nearest NRW-operated NRFA flow station using easting/northing coordinates.",
        "",
        "Method",
        f"High lead was defined as lead >= {thresholds.lead_high_ug_l:.3g} ug/L, the 75th percentile of the mine-related Pb/Zn paired samples.",
        f"Low zinc was defined as zinc <= {thresholds.zinc_low_ug_l:.3g} ug/L, the 25th percentile of the mine-related Pb/Zn paired samples.",
        f"High Pb/Zn ratio was defined as Pb/Zn >= {thresholds.pb_zn_high_ratio:.3g}, the 90th percentile of the paired samples.",
        "Low flow was defined using station-specific flow percentiles: daily flow percentile <= 25%. Very low flow used <= 10%.",
        "",
        "Key outputs",
        f"Total Pb/Zn paired water-quality samples: {n_pbzn:,}.",
        f"Samples with same-day matched NRFA flow: {n_flow:,}.",
        f"Low-flow samples with high Pb/Zn ratio: {n_low_flow_high_ratio:,}.",
        f"Low-flow samples with high Pb and low Zn: {n_low_flow_high_pb_low_zn:,}.",
        f"Systematic candidate stations identified: {n_candidates:,}.",
        "",
        "Top stations by low-flow high Pb/Zn behaviour",
    ]
    for _, row in top.iterrows():
        lines.append(
            f"{row['station_name']}: n_with_flow={int(row['n_with_flow'])}, "
            f"low-flow high Pb/Zn={int(row['n_low_flow_high_pbzn_ratio'])}, "
            f"low-flow high Pb/low Zn={int(row['n_low_flow_high_pb_low_zinc'])}, "
            f"median Pb/Zn={row['median_pb_zn_ratio']:.3g}."
        )
    lines.extend(
        [
            "",
            "Important limitation",
            "Nearest-flow-station matching is a first-pass method. It should be treated as hydrological context rather than proof that the gauged flow exactly represents each mine discharge point. The match distance is retained in the output tables for review.",
            "",
            "Next step",
            "Discuss with the supervisor whether to keep the nearest-station matching, restrict to closer matches, or manually match key mine sites to hydrologically appropriate gauging stations.",
        ]
    )

    def para(text: str) -> str:
        return f"<w:p><w:r><w:t>{escape(str(text))}</w:t></w:r></w:p>"

    body = "".join(para(line) for line in lines)
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    {body}
    <w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>
  </w:body>
</w:document>"""
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>"""
    with ZipFile(path, "w", ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document_xml)


def main() -> None:
    ensure_dirs()
    _, nrw_flow = download_nrfa_station_metadata()
    samples, thresholds = load_pbzn_samples()
    matches = match_water_stations_to_flow(samples, nrw_flow)

    matched_samples = samples.merge(
        matches[
            [
                "station_id",
                "nrfa_station_id",
                "nrfa_station_name",
                "nrfa_river",
                "nrfa_location",
                "nrfa_gdf_start_date",
                "nrfa_gdf_end_date",
                "nrfa_gdf_mean_flow_m3s",
                "flow_match_distance_km",
                "within_20km_flow_match",
            ]
        ],
        on="station_id",
        how="left",
    )
    flow_station_ids = matched_samples.loc[
        matched_samples["within_20km_flow_match"], "nrfa_station_id"
    ].dropna()
    flows = download_daily_flows(flow_station_ids.astype(int).tolist())
    merged = add_flow_percentiles(matched_samples, flows)
    merged.to_csv(PROCESSED / "pbzn_flow_matched_samples.csv", index=False)

    summary = station_summary(merged)
    summary.to_csv(PROCESSED / "pbzn_flow_station_summary.csv", index=False)
    thresholds_table = write_thresholds(thresholds, samples, merged)

    plot_ratio_vs_flow(merged)
    plot_ratio_by_flow_class(merged)
    plot_lead_zinc_flow_quadrants(merged, thresholds)
    plot_systematic_sites(summary)

    write_excel_exports(merged, summary, matches, thresholds_table)
    copy_figures_to_results()
    make_summary_docx(merged, summary, thresholds)

    print(f"Pb/Zn paired samples: {len(samples):,}")
    print(f"Samples with same-day NRFA flow: {int(merged['has_flow_match'].sum()):,}")
    print(f"NRW NRFA flow stations used: {matched_samples['nrfa_station_id'].nunique():,}")
    print(f"Systematic candidate stations: {int(summary['systematic_candidate'].sum()):,}")
    print(f"Wrote outputs to: {RESULTS}")


if __name__ == "__main__":
    main()
