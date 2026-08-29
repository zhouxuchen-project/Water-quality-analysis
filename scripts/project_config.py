from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
RAW_WATER_QUALITY_DIR = RAW_DIR / "nrw_water_quality"
RAW_STATIONS_DIR = RAW_DIR / "stations"
STATIONS_CSV = RAW_STATIONS_DIR / "nrw_water_quality_archive_stations.csv"
PROCESSED_DIR = DATA_DIR / "processed"
FIGURES_DIR = ROOT / "figures"
NOTES_DIR = ROOT / "notes"

TARGET_PARAMETERS = {
    "lead": {
        "label": "Lead",
        "patterns": [r"\blead\b", r"\bpb\b"],
        "ratio_group": "metal",
    },
    "zinc": {
        "label": "Zinc",
        "patterns": [r"\bzinc\b", r"\bzn\b"],
        "ratio_group": "metal",
    },
    "copper": {
        "label": "Copper",
        "patterns": [r"\bcopper\b", r"\bcu\b"],
        "ratio_group": "metal",
    },
    "calcium": {
        "label": "Calcium",
        "patterns": [r"\bcalcium\b", r"\bca\b"],
        "ratio_group": "supporting",
    },
    "ph": {
        "label": "pH",
        "patterns": [r"^ph($|\s)"],
        "ratio_group": "supporting",
    },
    "hardness": {
        "label": "Hardness",
        "patterns": [r"\bhardness\b"],
        "ratio_group": "supporting",
    },
}

DATE_COLUMNS = [
    "sample_date",
    "sampling_date",
    "date_sampled",
    "date_taken",
    "sample_datetime",
    "sampling_datetime",
    "date",
]

STATION_ID_COLUMNS = [
    "station_number",
    "station_code",
    "station_id",
    "site_id",
    "sampling_point",
    "sampling_point_id",
    "monitoring_point",
    "monitoring_point_id",
]

STATION_NAME_COLUMNS = [
    "station_name",
    "site_name",
    "sampling_point_name",
    "monitoring_point_name",
    "location_name",
]

PARAMETER_COLUMNS = [
    "determinand",
    "determinand_label",
    "parameter_name",
    "parameter",
    "parameter_shortname",
    "analyte",
    "substance",
    "substance_name",
    "measurement",
    "test_name",
]

VALUE_COLUMNS = [
    "result",
    "result_value",
    "result_numeric",
    "numeric_result",
    "sample_value",
    "coded_value",
    "value",
    "measurement_value",
    "concentration",
]

UNIT_COLUMNS = ["unit", "units", "unit_name", "unit_symbol", "result_unit", "unit_of_measurement", "uom"]
QUALIFIER_COLUMNS = ["qualifier", "result_qualifier", "symbol", "sign", "less_than"]


def ensure_directories() -> None:
    for path in [
        RAW_WATER_QUALITY_DIR,
        RAW_STATIONS_DIR,
        PROCESSED_DIR,
        FIGURES_DIR,
        NOTES_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def normalise_column_name(name: object) -> str:
    text = str(name).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text


def normalise_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = text.strip().lower()
    text = text.replace("µ", "u")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def first_existing(columns: list[str], candidates: list[str]) -> str | None:
    column_set = set(columns)
    for candidate in candidates:
        if candidate in column_set:
            return candidate
    return None


def canonical_parameter(value: object) -> str | None:
    text = normalise_text(value)
    if not text:
        return None

    matching_order = ["lead", "zinc", "copper", "hardness", "calcium", "ph"]
    for key in matching_order:
        spec = TARGET_PARAMETERS[key]
        for pattern in spec["patterns"]:
            if re.search(pattern.lower(), text):
                return key
    return None
