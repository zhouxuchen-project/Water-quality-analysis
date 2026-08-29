from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from project_config import FIGURES_DIR, PROCESSED_DIR, STATIONS_CSV, ensure_directories


def split_sampling_years(value: object) -> list[int]:
    if pd.isna(value):
        return []
    years = []
    for part in str(value).replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            years.append(int(part))
    return years


def main() -> None:
    ensure_directories()
    if not STATIONS_CSV.exists():
        raise FileNotFoundError(
            f"Station file not found: {STATIONS_CSV}. Run scripts/00_download_stations.py first."
        )

    stations = pd.read_csv(STATIONS_CSV)
    stations["sampling_year_list"] = stations["sampling_years"].apply(split_sampling_years)
    stations["first_sampling_year"] = stations["sampling_year_list"].apply(
        lambda years: min(years) if years else pd.NA
    )
    stations["last_sampling_year"] = stations["sampling_year_list"].apply(
        lambda years: max(years) if years else pd.NA
    )
    stations["n_sampling_years"] = stations["sampling_year_list"].apply(len)

    type_summary = (
        stations.groupby("station_type", dropna=False)
        .agg(
            n_stations=("station_number", "count"),
            median_sampling_years=("n_sampling_years", "median"),
            earliest_year=("first_sampling_year", "min"),
            latest_year=("last_sampling_year", "max"),
        )
        .sort_values("n_stations", ascending=False)
    )
    type_summary.to_csv(PROCESSED_DIR / "station_summary_by_type.csv")

    catchment_summary = (
        stations.groupby("wfd_c2_mgt_catchment_name", dropna=False)
        .agg(
            n_stations=("station_number", "count"),
            median_sampling_years=("n_sampling_years", "median"),
            earliest_year=("first_sampling_year", "min"),
            latest_year=("last_sampling_year", "max"),
        )
        .sort_values("n_stations", ascending=False)
    )
    catchment_summary.to_csv(PROCESSED_DIR / "station_summary_by_catchment.csv")

    mining_keywords = r"mine|mining|minewater|colliery|adit|shaft|metal|lead|zinc|copper"
    stations["mining_related_hint"] = (
        stations["station_type"].astype(str).str.contains(mining_keywords, case=False, regex=True, na=False)
        | stations["station_name"].astype(str).str.contains(mining_keywords, case=False, regex=True, na=False)
    )
    mining_related = stations[stations["mining_related_hint"]].copy()
    mining_summary = (
        mining_related.groupby("station_type", dropna=False)
        .agg(
            n_stations=("station_number", "count"),
            n_catchments=("wfd_c2_mgt_catchment_name", "nunique"),
            median_sampling_years=("n_sampling_years", "median"),
            earliest_year=("first_sampling_year", "min"),
            latest_year=("last_sampling_year", "max"),
        )
        .sort_values("n_stations", ascending=False)
    )
    mining_summary.to_csv(PROCESSED_DIR / "mining_related_station_summary.csv")

    top_types = type_summary.head(12).reset_index()
    plt.figure(figsize=(11, 6))
    sns.barplot(data=top_types, y="station_type", x="n_stations", color="#4477AA")
    plt.xlabel("Number of stations")
    plt.ylabel("")
    plt.title("NRW Water Quality Archive: top station types")
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "station_types_top12.png", dpi=200)
    plt.close()

    map_data = stations.dropna(subset=["easting", "northing"]).copy()
    plt.figure(figsize=(7, 8))
    sns.scatterplot(
        data=map_data,
        x="easting",
        y="northing",
        hue="wfd_c2_mgt_catchment_name",
        s=8,
        linewidth=0,
        alpha=0.55,
        legend=False,
    )
    plt.xlabel("British National Grid easting")
    plt.ylabel("British National Grid northing")
    plt.title("NRW water quality monitoring stations in Wales")
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "station_locations_wales.png", dpi=220)
    plt.close()

    plt.figure(figsize=(7, 8))
    sns.scatterplot(
        data=map_data,
        x="easting",
        y="northing",
        color="#D0D0D0",
        s=7,
        linewidth=0,
        alpha=0.35,
    )
    mining_map_data = mining_related.dropna(subset=["easting", "northing"])
    sns.scatterplot(
        data=mining_map_data,
        x="easting",
        y="northing",
        color="#CC6677",
        s=16,
        linewidth=0,
        alpha=0.8,
    )
    plt.xlabel("British National Grid easting")
    plt.ylabel("British National Grid northing")
    plt.title("Mining-related station hints in the NRW archive")
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "mining_related_station_hints.png", dpi=220)
    plt.close()

    print(f"Stations: {len(stations):,}")
    print(f"Station types: {stations['station_type'].nunique(dropna=True):,}")
    print(f"Catchments: {stations['wfd_c2_mgt_catchment_name'].nunique(dropna=True):,}")
    print(f"Mining-related station hints: {len(mining_related):,}")
    print(f"Wrote summaries to: {PROCESSED_DIR}")
    print(f"Wrote figures to: {FIGURES_DIR}")


if __name__ == "__main__":
    main()
