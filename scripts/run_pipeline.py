from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"

ANALYSIS_SCRIPTS = [
    "00_download_stations.py",
    "02_profile_raw_water_quality.py",
    "03_clean_water_quality.py",
    "13_audit_nrw_quality_flags.py",
    "01_station_overview.py",
    "04_exploratory_analysis.py",
    "06_compare_all_vs_mine.py",
    "07_mine_related_analysis.py",
    "08_pbzn_flow_analysis.py",
    "10_manual_flow_matching_validation.py",
    "14_pbzn_censoring_sensitivity.py",
    "15_flow_window_sensitivity.py",
    "16_create_thesis_figures_tables.py",
    "29_complete_final_analysis.py",
    "17_other_metals_flow_extension.py",
]

FIGURE_SCRIPTS = [
    "18_generate_introduction_schematics.py",
    "19_regenerate_figure_4_5_manual_validation.py",
    "20_regenerate_figure_a_4_multi_metal_scatterplots.py",
    "21_build_dissertation_figure_pack.py",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Welsh mine-water analysis in its reproducible order."
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List the selected scripts without running them.",
    )
    parser.add_argument(
        "--start",
        metavar="PREFIX",
        help="Start at a script filename or numeric prefix, for example 07.",
    )
    parser.add_argument(
        "--stop",
        metavar="PREFIX",
        help="Stop after a script filename or numeric prefix, for example 14.",
    )
    parser.add_argument(
        "--with-figures",
        action="store_true",
        help="Run the optional final figure scripts after the analysis.",
    )
    parser.add_argument(
        "--figures-only",
        action="store_true",
        help="Run only the optional final figure scripts.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing them.",
    )
    return parser.parse_args()


def select_range(scripts: list[str], start: str | None, stop: str | None) -> list[str]:
    selected = scripts
    if start:
        try:
            start_index = next(
                index for index, name in enumerate(selected) if name == start or name.startswith(start)
            )
        except StopIteration as exc:
            raise SystemExit(f"No script matches --start {start!r}.") from exc
        selected = selected[start_index:]

    if stop:
        try:
            stop_index = next(
                index for index, name in enumerate(selected) if name == stop or name.startswith(stop)
            )
        except StopIteration as exc:
            raise SystemExit(f"No selected script matches --stop {stop!r}.") from exc
        selected = selected[: stop_index + 1]
    return selected


def validate_scripts(scripts: list[str]) -> None:
    missing = [name for name in scripts if not (SCRIPT_DIR / name).is_file()]
    if missing:
        raise SystemExit("Missing pipeline scripts: " + ", ".join(missing))


def main() -> None:
    args = parse_args()
    scripts = FIGURE_SCRIPTS if args.figures_only else list(ANALYSIS_SCRIPTS)
    if args.with_figures and not args.figures_only:
        scripts.extend(FIGURE_SCRIPTS)
    scripts = select_range(scripts, args.start, args.stop)
    validate_scripts(scripts)

    if args.list:
        for index, name in enumerate(scripts, start=1):
            print(f"{index:02d}. {name}")
        return

    for name in scripts:
        command = [sys.executable, str(SCRIPT_DIR / name)]
        print(f"\n=== Running {name} ===", flush=True)
        if args.dry_run:
            print(f"python scripts\\{name}")
            continue
        subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
