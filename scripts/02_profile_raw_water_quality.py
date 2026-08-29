from __future__ import annotations

from pathlib import Path
import re
from zipfile import ZipFile

import pandas as pd

from project_config import (
    NOTES_DIR,
    PARAMETER_COLUMNS,
    PROCESSED_DIR,
    RAW_WATER_QUALITY_DIR,
    VALUE_COLUMNS,
    ensure_directories,
    first_existing,
    normalise_column_name,
)


SUPPORTED_EXTENSIONS = {".csv", ".txt", ".tsv", ".xlsx", ".xls", ".zip"}
SUPPORTED_TABLE_EXTENSIONS = {".csv", ".txt", ".tsv", ".xlsx", ".xls"}


def raw_files() -> list[Path]:
    return sorted(
        path
        for path in RAW_WATER_QUALITY_DIR.rglob("*")
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_EXTENSIONS
        and "file list" not in path.name.lower()
        and path.name.lower() != "nrw_water_quality_by_year.zip"
    )


def read_preview(path: Path, nrows: int = 500) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".zip":
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
            if not table_names:
                raise ValueError("ZIP contains no supported CSV/XLSX files")
            inner_name = table_names[0]
            with archive.open(inner_name) as handle:
                inner_suffix = Path(inner_name).suffix.lower()
                if inner_suffix in {".xlsx", ".xls"}:
                    return pd.read_excel(handle, nrows=nrows)
                if inner_suffix == ".tsv":
                    return pd.read_csv(handle, sep="\t", nrows=nrows, low_memory=False)
                return pd.read_csv(handle, nrows=nrows, low_memory=False)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path, nrows=nrows)
    if suffix == ".tsv":
        return pd.read_csv(path, sep="\t", nrows=nrows, low_memory=False)
    for encoding in ["utf-8-sig", "utf-8", "cp1252", "latin1"]:
        try:
            return pd.read_csv(path, nrows=nrows, low_memory=False, encoding=encoding)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path, nrows=nrows, low_memory=False, encoding="latin1")


def estimate_rows(path: Path) -> int | None:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls", ".zip"}:
        return None
    try:
        with path.open("rb") as handle:
            return max(sum(1 for _ in handle) - 1, 0)
    except OSError:
        return None


def main() -> None:
    ensure_directories()
    files = raw_files()
    if not files:
        print(f"No raw water quality files found in: {RAW_WATER_QUALITY_DIR}")
        print("Download NRW water quality files and place them in that folder, then rerun this script.")
        return

    rows = []
    parameter_rows = []
    for path in files:
        try:
            preview = read_preview(path)
        except Exception as exc:
            rows.append(
                {
                    "file": str(path.relative_to(RAW_WATER_QUALITY_DIR)),
                    "status": f"read_error: {exc}",
                    "estimated_rows": estimate_rows(path),
                    "n_columns": None,
                    "columns": None,
                    "parameter_column": None,
                    "value_column": None,
                }
            )
            continue

        preview.columns = [normalise_column_name(col) for col in preview.columns]
        parameter_col = first_existing(list(preview.columns), PARAMETER_COLUMNS)
        value_col = first_existing(list(preview.columns), VALUE_COLUMNS)
        rows.append(
            {
                "file": str(path.relative_to(RAW_WATER_QUALITY_DIR)),
                "status": "ok",
                "estimated_rows": estimate_rows(path),
                "n_columns": len(preview.columns),
                "columns": ", ".join(preview.columns),
                "parameter_column": parameter_col,
                "value_column": value_col,
            }
        )

        if parameter_col:
            counts = preview[parameter_col].astype(str).value_counts(dropna=False).head(80)
            for parameter, count in counts.items():
                parameter_rows.append(
                    {
                        "file": str(path.relative_to(RAW_WATER_QUALITY_DIR)),
                        "parameter_preview": parameter,
                        "preview_count": int(count),
                    }
                )

    profile = pd.DataFrame(rows)
    profile.to_csv(PROCESSED_DIR / "raw_water_quality_file_profile.csv", index=False)

    if parameter_rows:
        pd.DataFrame(parameter_rows).to_csv(
            PROCESSED_DIR / "raw_water_quality_parameter_preview.csv", index=False
        )

    note_lines = [
        "# Raw Water Quality File Profile",
        "",
        f"Files checked: {len(files)}",
        "",
        "This profile is used to confirm the real column names before cleaning.",
        "",
    ]
    for row in rows:
        note_lines.extend(
            [
                f"## {row['file']}",
                "",
                f"- Status: {row['status']}",
                f"- Estimated rows: {row['estimated_rows']}",
                f"- Columns: {row['columns']}",
                f"- Detected parameter column: {row['parameter_column']}",
                f"- Detected value column: {row['value_column']}",
                "",
            ]
        )
    (NOTES_DIR / "raw_water_quality_file_profile.md").write_text(
        "\n".join(note_lines), encoding="utf-8"
    )

    print(f"Profiled {len(files):,} raw files.")
    print(f"Wrote: {PROCESSED_DIR / 'raw_water_quality_file_profile.csv'}")
    print(f"Wrote: {NOTES_DIR / 'raw_water_quality_file_profile.md'}")


if __name__ == "__main__":
    main()
