from __future__ import annotations

import re
from pathlib import Path
from zipfile import ZipFile

import pandas as pd

from project_config import (
    DATE_COLUMNS,
    PARAMETER_COLUMNS,
    PROCESSED_DIR,
    QUALIFIER_COLUMNS,
    RAW_WATER_QUALITY_DIR,
    STATION_ID_COLUMNS,
    STATION_NAME_COLUMNS,
    STATIONS_CSV,
    TARGET_PARAMETERS,
    UNIT_COLUMNS,
    VALUE_COLUMNS,
    canonical_parameter,
    ensure_directories,
    first_existing,
    normalise_column_name,
)


SUPPORTED_EXTENSIONS = {".csv", ".txt", ".tsv", ".xlsx", ".xls", ".zip"}
SUPPORTED_TABLE_EXTENSIONS = {".csv", ".txt", ".tsv", ".xlsx", ".xls"}
NON_WATER_MEDIUM_PATTERN = re.compile(
    r"sediment|tissue|whole animal|mussel|crayfish|roach|trout|flounder|dab|biota",
    flags=re.IGNORECASE,
)


def raw_files() -> list[Path]:
    return sorted(
        path
        for path in RAW_WATER_QUALITY_DIR.rglob("*")
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_EXTENSIONS
        and "file list" not in path.name.lower()
        and path.name.lower() != "nrw_water_quality_by_year.zip"
    )


def read_file(path: Path) -> list[tuple[str, pd.DataFrame]]:
    suffix = path.suffix.lower()
    if suffix == ".zip":
        frames = []
        with ZipFile(path) as archive:
            table_names = [
                name
                for name in archive.namelist()
                if Path(name).suffix.lower() in SUPPORTED_TABLE_EXTENSIONS
                and not Path(name).name.startswith("~$")
                and "file list" not in Path(name).name.lower()
            ]
            year_table_names = [
                name for name in table_names if re.match(r"^\d{4}\b", Path(name).name)
            ]
            table_names = year_table_names or table_names
            for inner_name in table_names:
                inner_suffix = Path(inner_name).suffix.lower()
                with archive.open(inner_name) as handle:
                    if inner_suffix in {".xlsx", ".xls"}:
                        sheets = pd.read_excel(handle, sheet_name=None)
                        for sheet_name, frame in sheets.items():
                            frames.append((f"{path.name}::{inner_name}#{sheet_name}", frame))
                    elif inner_suffix == ".tsv":
                        frames.append(
                            (
                                f"{path.name}::{inner_name}",
                                pd.read_csv(handle, sep="\t", low_memory=False),
                            )
                        )
                    else:
                        frames.append(
                            (
                                f"{path.name}::{inner_name}",
                                pd.read_csv(handle, low_memory=False),
                            )
                        )
        return frames
    if suffix in {".xlsx", ".xls"}:
        sheets = pd.read_excel(path, sheet_name=None)
        frames = []
        for sheet_name, frame in sheets.items():
            frames.append((f"{path.name}#{sheet_name}", frame))
        return frames
    if suffix == ".tsv":
        return [(path.name, pd.read_csv(path, sep="\t", low_memory=False))]
    for encoding in ["utf-8-sig", "utf-8", "cp1252", "latin1"]:
        try:
            return [(path.name, pd.read_csv(path, low_memory=False, encoding=encoding))]
        except UnicodeDecodeError:
            continue
    return [(path.name, pd.read_csv(path, low_memory=False, encoding="latin1"))]


def parse_numeric_result(value: object) -> tuple[float | None, bool]:
    if pd.isna(value):
        return None, False
    text = str(value).strip()
    censored = text.startswith("<") or text.lower().startswith("less than")
    cleaned = text.replace(",", "")
    match = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", cleaned)
    if not match:
        return None, censored
    return float(match.group(0)), censored


def optional_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column in frame.columns:
        return frame[column].astype(str).str.strip()
    return pd.Series(pd.NA, index=frame.index)


def clean_long_format(frame: pd.DataFrame, source_file: str) -> pd.DataFrame | None:
    frame = frame.copy()
    frame.columns = [normalise_column_name(col) for col in frame.columns]
    columns = list(frame.columns)

    date_col = first_existing(columns, DATE_COLUMNS)
    station_id_col = first_existing(columns, STATION_ID_COLUMNS)
    station_name_col = first_existing(columns, STATION_NAME_COLUMNS)
    parameter_col = first_existing(columns, PARAMETER_COLUMNS)
    value_col = first_existing(columns, VALUE_COLUMNS)
    unit_col = first_existing(columns, UNIT_COLUMNS)
    qualifier_col = first_existing(columns, QUALIFIER_COLUMNS)

    if not (parameter_col and value_col):
        return None

    canonical = frame[parameter_col].apply(canonical_parameter)
    keep_mask = canonical.isin(TARGET_PARAMETERS)
    if not keep_mask.any():
        return pd.DataFrame()

    frame = frame.loc[keep_mask].copy()
    canonical = canonical.loc[keep_mask]

    parsed_values = frame[value_col].apply(parse_numeric_result)
    cleaned = pd.DataFrame(
        {
            "sample_date": pd.to_datetime(frame[date_col], errors="coerce")
            if date_col
            else pd.NaT,
            "station_id": frame[station_id_col].astype(str).str.strip()
            if station_id_col
            else pd.NA,
            "station_name": frame[station_name_col].astype(str).str.strip()
            if station_name_col
            else pd.NA,
            "raw_parameter": frame[parameter_col].astype(str).str.strip(),
            "canonical_parameter": canonical,
            "value": [item[0] for item in parsed_values],
            "censored": [item[1] for item in parsed_values],
            "unit": frame[unit_col].astype(str).str.strip() if unit_col else pd.NA,
            "qualifier": frame[qualifier_col].astype(str).str.strip() if qualifier_col else pd.NA,
            "sampling_medium": optional_series(frame, "sampling_medium"),
            "sampling_reason": optional_series(frame, "sampling_reason"),
            "reason_group": optional_series(frame, "reason_group"),
            "method_name": optional_series(frame, "method_name"),
            "raw_station_type": optional_series(frame, "station_type"),
            "source_file": source_file,
        }
    )
    return cleaned


def clean_wide_format(frame: pd.DataFrame, source_file: str) -> pd.DataFrame | None:
    frame = frame.copy()
    frame.columns = [normalise_column_name(col) for col in frame.columns]
    columns = list(frame.columns)

    date_col = first_existing(columns, DATE_COLUMNS)
    station_id_col = first_existing(columns, STATION_ID_COLUMNS)
    station_name_col = first_existing(columns, STATION_NAME_COLUMNS)

    value_columns = {}
    for column in columns:
        canonical = canonical_parameter(column)
        if canonical:
            value_columns[column] = canonical

    if not value_columns:
        return None

    id_columns = [col for col in [date_col, station_id_col, station_name_col] if col]
    melted = frame.melt(
        id_vars=id_columns,
        value_vars=list(value_columns),
        var_name="raw_parameter",
        value_name="raw_value",
    )
    parsed_values = melted["raw_value"].apply(parse_numeric_result)
    cleaned = pd.DataFrame(
        {
            "sample_date": pd.to_datetime(melted[date_col], errors="coerce")
            if date_col
            else pd.NaT,
            "station_id": melted[station_id_col].astype(str).str.strip()
            if station_id_col
            else pd.NA,
            "station_name": melted[station_name_col].astype(str).str.strip()
            if station_name_col
            else pd.NA,
            "raw_parameter": melted["raw_parameter"],
            "canonical_parameter": melted["raw_parameter"].map(value_columns),
            "value": [item[0] for item in parsed_values],
            "censored": [item[1] for item in parsed_values],
            "unit": pd.NA,
            "qualifier": pd.NA,
            "sampling_medium": optional_series(melted, "sampling_medium"),
            "sampling_reason": optional_series(melted, "sampling_reason"),
            "reason_group": optional_series(melted, "reason_group"),
            "method_name": optional_series(melted, "method_name"),
            "raw_station_type": optional_series(melted, "station_type"),
            "source_file": source_file,
        }
    )
    return cleaned


def add_standard_units_and_qc(cleaned: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    cleaned = cleaned.copy()
    unit_text = cleaned["unit"].astype(str).str.lower()
    parameter = cleaned["canonical_parameter"]
    value = cleaned["value"]

    cleaned["value_standardised"] = pd.NA
    cleaned["standard_unit"] = pd.NA
    cleaned["qc_exclusion_reason"] = pd.NA

    metal_mask = parameter.isin(["lead", "zinc", "copper"])
    metal_ugl = metal_mask & unit_text.str.contains("microgram per litre", na=False)
    metal_mgl = metal_mask & unit_text.str.contains("milligram per litre", na=False)
    cleaned.loc[metal_ugl, "value_standardised"] = value.loc[metal_ugl]
    cleaned.loc[metal_mgl, "value_standardised"] = value.loc[metal_mgl] * 1000
    cleaned.loc[metal_ugl | metal_mgl, "standard_unit"] = "ug/L"

    mg_l_mask = parameter.isin(["calcium", "hardness"]) & unit_text.str.contains(
        "milligram per litre", na=False
    )
    cleaned.loc[mg_l_mask, "value_standardised"] = value.loc[mg_l_mask]
    cleaned.loc[mg_l_mask, "standard_unit"] = "mg/L"

    ph_mask = parameter.eq("ph") & unit_text.str.contains("scalar", na=False)
    cleaned.loc[ph_mask, "value_standardised"] = value.loc[ph_mask]
    cleaned.loc[ph_mask, "standard_unit"] = "pH"

    unsupported_unit = cleaned["value_standardised"].isna()
    cleaned.loc[unsupported_unit, "qc_exclusion_reason"] = "unsupported_unit_for_parameter"

    non_water = cleaned["sampling_medium"].astype(str).str.contains(NON_WATER_MEDIUM_PATTERN, na=False)
    cleaned.loc[non_water, "qc_exclusion_reason"] = "non_water_sampling_medium"

    standard_values = pd.to_numeric(cleaned["value_standardised"], errors="coerce")

    invalid_ph = parameter.eq("ph") & ~(standard_values.gt(0) & standard_values.le(14))
    cleaned.loc[invalid_ph, "qc_exclusion_reason"] = "invalid_ph_range"

    negative = parameter.ne("ph") & standard_values.lt(0)
    cleaned.loc[negative, "qc_exclusion_reason"] = "negative_value"

    excluded = cleaned[cleaned["qc_exclusion_reason"].notna()].copy()
    valid = cleaned[cleaned["qc_exclusion_reason"].isna()].copy()
    valid["value_standardised"] = valid["value_standardised"].astype(float)
    return valid, excluded


def add_station_metadata(cleaned: pd.DataFrame) -> pd.DataFrame:
    if not STATIONS_CSV.exists() or "station_id" not in cleaned.columns:
        return cleaned

    stations = pd.read_csv(STATIONS_CSV, dtype={"station_number": "string"})
    station_columns = [
        "station_number",
        "station_status",
        "station_type",
        "easting",
        "northing",
        "wfd_c2_mgt_catchment_name",
    ]
    station_columns = [col for col in station_columns if col in stations.columns]
    stations = stations[station_columns].drop_duplicates("station_number")
    stations["station_number"] = stations["station_number"].astype(str).str.strip()

    cleaned = cleaned.copy()
    cleaned["station_id"] = cleaned["station_id"].astype(str).str.strip()
    return cleaned.merge(
        stations,
        left_on="station_id",
        right_on="station_number",
        how="left",
    ).drop(columns=["station_number"], errors="ignore")


def main() -> None:
    ensure_directories()
    files = raw_files()
    if not files:
        print(f"No raw water quality files found in: {RAW_WATER_QUALITY_DIR}")
        print("Download NRW water quality files and place them in that folder, then rerun this script.")
        return

    cleaned_frames = []
    unreadable = []
    for path in files:
        try:
            frames = read_file(path)
        except Exception as exc:
            unreadable.append((path.name, str(exc)))
            continue

        for source, frame in frames:
            cleaned = clean_long_format(frame, source)
            if cleaned is None:
                cleaned = clean_wide_format(frame, source)
            if cleaned is not None and not cleaned.empty:
                cleaned_frames.append(cleaned)

    if not cleaned_frames:
        raise RuntimeError(
            "No usable water quality table was detected. Run scripts/02_profile_raw_water_quality.py "
            "and check the detected column names."
        )

    cleaned = pd.concat(cleaned_frames, ignore_index=True)
    cleaned = cleaned[cleaned["canonical_parameter"].isin(TARGET_PARAMETERS)]
    cleaned = cleaned.dropna(subset=["value"])
    cleaned = cleaned.drop_duplicates()
    cleaned = add_station_metadata(cleaned)
    cleaned, qc_excluded = add_standard_units_and_qc(cleaned)

    long_csv = PROCESSED_DIR / "water_quality_selected_long.csv"
    long_parquet = PROCESSED_DIR / "water_quality_selected_long.parquet"
    cleaned.to_csv(long_csv, index=False)
    cleaned.to_parquet(long_parquet, index=False)
    qc_excluded.to_csv(PROCESSED_DIR / "water_quality_qc_excluded_records.csv", index=False)

    wide = (
        cleaned.groupby(["station_id", "station_name", "sample_date", "canonical_parameter"], dropna=False)[
            "value_standardised"
        ]
        .mean()
        .reset_index()
        .pivot_table(
            index=["station_id", "station_name", "sample_date"],
            columns="canonical_parameter",
            values="value_standardised",
            aggfunc="mean",
        )
        .reset_index()
    )
    wide.columns.name = None
    wide.to_csv(PROCESSED_DIR / "water_quality_selected_wide.csv", index=False)

    coverage = (
        cleaned.groupby("canonical_parameter")
        .agg(
            n_records=("value", "size"),
            n_stations=("station_id", "nunique"),
            first_date=("sample_date", "min"),
            last_date=("sample_date", "max"),
            median=("value_standardised", "median"),
            minimum=("value_standardised", "min"),
            maximum=("value_standardised", "max"),
        )
        .sort_values("n_records", ascending=False)
    )
    coverage.to_csv(PROCESSED_DIR / "parameter_coverage_summary.csv")

    print(f"Cleaned rows: {len(cleaned):,}")
    print(f"QC excluded rows: {len(qc_excluded):,}")
    print(f"Wide sample rows: {len(wide):,}")
    print(f"Wrote: {long_csv}")
    print(f"Wrote: {PROCESSED_DIR / 'water_quality_selected_wide.csv'}")
    if unreadable:
        print("Unreadable files:")
        for filename, error in unreadable:
            print(f"- {filename}: {error}")


if __name__ == "__main__":
    main()
