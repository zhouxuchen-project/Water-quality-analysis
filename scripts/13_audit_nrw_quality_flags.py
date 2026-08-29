from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from zipfile import ZipFile

import pandas as pd

from project_config import PROCESSED_DIR, RAW_WATER_QUALITY_DIR, canonical_parameter


ANNUAL_DIR = RAW_WATER_QUALITY_DIR / "by_year"
OUTPUT_SUMMARY = PROCESSED_DIR / "raw_quality_flag_audit.csv"
OUTPUT_VALUES = PROCESSED_DIR / "raw_quality_flag_values.csv"
OUTPUT_DEVIATING = PROCESSED_DIR / "raw_deviating_target_records.csv"


def normalise_flag(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip().lower()


def is_deviating(value: object) -> bool:
    text = normalise_flag(value)
    return text not in {"", "0", "false", "f", "n", "no", "none", "nan"}


def is_less_than(value: object) -> bool:
    text = normalise_flag(value)
    return text in {"<", "less than", "lt"} or text.startswith("<")


def main() -> None:
    counters: dict[str, Counter[str]] = defaultdict(Counter)
    value_counters: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    deviating_rows: list[pd.DataFrame] = []

    annual_files = sorted(ANNUAL_DIR.glob("* Water Quality Archive.zip"))
    if not annual_files:
        raise FileNotFoundError(f"No annual NRW archives found in {ANNUAL_DIR}")

    for archive_path in annual_files:
        with ZipFile(archive_path) as archive:
            csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            for csv_name in csv_names:
                with archive.open(csv_name) as handle:
                    wanted = [
                        "parameter_name",
                        "parameter_shortname",
                        "sample_value",
                        "deviating_result",
                        "sign",
                        "unit_name",
                        "sampling_medium",
                        "station_number",
                        "station_name",
                        "sampling_datetime",
                    ]
                    for chunk in pd.read_csv(
                        handle,
                        usecols=lambda name: name in wanted,
                        chunksize=250_000,
                        low_memory=False,
                    ):
                        parameter_source = (
                            chunk["parameter_name"]
                            if "parameter_name" in chunk.columns
                            else chunk["parameter_shortname"]
                        )
                        parameter_map = {
                            value: canonical_parameter(value)
                            for value in parameter_source.drop_duplicates()
                        }
                        canonical = parameter_source.map(parameter_map)
                        keep = canonical.notna()
                        if not keep.any():
                            continue

                        selected = chunk.loc[keep].copy()
                        selected["canonical_parameter"] = canonical.loc[keep]
                        for parameter, group in selected.groupby("canonical_parameter"):
                            counters[parameter]["raw_target_records"] += len(group)

                            deviating = group.get(
                                "deviating_result", pd.Series("", index=group.index)
                            ).map(is_deviating)
                            less_than = group.get("sign", pd.Series("", index=group.index)).map(
                                is_less_than
                            )
                            value_text_lt = group.get(
                                "sample_value", pd.Series("", index=group.index)
                            ).astype(str).str.strip().str.startswith("<")

                            counters[parameter]["deviating_records"] += int(deviating.sum())
                            counters[parameter]["sign_less_than_records"] += int(less_than.sum())
                            counters[parameter]["value_text_less_than_records"] += int(
                                value_text_lt.sum()
                            )
                            counters[parameter]["less_than_missed_by_value_text"] += int(
                                (less_than & ~value_text_lt).sum()
                            )
                            counters[parameter]["deviating_and_less_than"] += int(
                                (deviating & less_than).sum()
                            )

                            if deviating.any():
                                columns = [
                                    "station_number",
                                    "station_name",
                                    "sampling_datetime",
                                    "parameter_shortname",
                                    "parameter_name",
                                    "sample_value",
                                    "unit_name",
                                    "sign",
                                    "sampling_medium",
                                    "deviating_result",
                                ]
                                columns = [column for column in columns if column in group.columns]
                                flagged = group.loc[deviating, columns].copy()
                                flagged.insert(0, "canonical_parameter", parameter)
                                flagged.insert(0, "source_archive", archive_path.name)
                                deviating_rows.append(flagged)

                            for field in [
                                "deviating_result",
                                "sign",
                                "unit_name",
                                "sampling_medium",
                            ]:
                                if field not in group.columns:
                                    continue
                                values = group[field].map(normalise_flag)
                                value_counters[(parameter, field)].update(values.tolist())

        print(f"Audited {archive_path.name}", flush=True)

    summary_rows = []
    for parameter in sorted(counters):
        record = {"parameter": parameter, **counters[parameter]}
        total = record["raw_target_records"]
        record["deviating_percent"] = 100 * record["deviating_records"] / total
        record["less_than_percent"] = 100 * record["sign_less_than_records"] / total
        summary_rows.append(record)
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(OUTPUT_SUMMARY, index=False)

    value_rows = []
    for (parameter, field), counts in sorted(value_counters.items()):
        for value, count in counts.most_common():
            value_rows.append(
                {
                    "parameter": parameter,
                    "field": field,
                    "value": value,
                    "count": count,
                }
            )
    pd.DataFrame(value_rows).to_csv(OUTPUT_VALUES, index=False)
    deviations = (
        pd.concat(deviating_rows, ignore_index=True)
        if deviating_rows
        else pd.DataFrame()
    )
    deviations.to_csv(OUTPUT_DEVIATING, index=False)

    print(summary.to_string(index=False))
    print(f"Wrote {OUTPUT_SUMMARY}")
    print(f"Wrote {OUTPUT_VALUES}")
    print(f"Wrote {OUTPUT_DEVIATING}")


if __name__ == "__main__":
    main()
