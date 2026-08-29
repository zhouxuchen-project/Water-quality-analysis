# Mining the Data, Cleaning the Mining

Reproducible Python code for the MSc dissertation:

**Mining the Data, Cleaning the Mining: Mining Remediation through Understanding River Flow and Water-Quality Data**

The workflow analyses Natural Resources Wales (NRW) water-quality records from mine-related stations in Wales. It begins with Pb, Zn, Cu, Ca, pH and hardness, focuses on Pb/Zn under different flow conditions, validates automated National River Flow Archive (NRFA) gauge matching, and extends the final interpretation using Cu/Zn and Pb/Cu.

This is a **code-only repository**. Raw and processed data, generated results, figures, spreadsheets, Word documents and the dissertation itself are deliberately excluded.

## Repository contents

```text
scripts/             Data preparation, analysis, validation and figure code
requirements.txt     Python package requirements
.gitignore           Prevents data and generated outputs from being committed
README.md            Setup, execution order and reproducibility notes
```

The repository includes all code needed for the reported scientific workflow. One-off scripts used only to format emails, meeting documents or dissertation Word files are not part of the analytical repository.

## Software

- Python 3.10 or newer
- Internet access for the first retrieval of NRW station metadata and NRFA records

From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Data setup

Obtain the NRW Water Quality Archive files from the official NRW/DataMap Wales source. Place the annual archive files in:

```text
data/raw/nrw_water_quality/by_year/
```

The cleaning code accepts CSV, TSV, Excel and ZIP inputs. Annual ZIP files such as `2000 Water Quality Archive.zip` through `2026 Water Quality Archive.zip` can be placed directly in the folder above.

Station metadata are downloaded by `00_download_stations.py`. NRFA station metadata and daily mean flow series are retrieved and cached by the flow-analysis scripts using the official NRFA API.

The scripts create these local folders as required:

```text
data/raw/stations/          NRW station metadata
data/raw/river_flow/        Downloaded NRFA metadata and daily flow series
data/processed/             Cleaned and intermediate datasets
figures/                    Exploratory figures
results/                    Analysis tables, validation outputs and final figures
notes/                      Local audit notes
```

All these data and output folders are ignored by Git.

## Run the workflow

List the reproducible analysis sequence:

```powershell
python scripts\run_pipeline.py --list
```

Run the complete analytical workflow after placing the NRW annual files in the expected folder:

```powershell
python scripts\run_pipeline.py
```

Run only a selected range, for example from mine-related analysis through censoring sensitivity:

```powershell
python scripts\run_pipeline.py --start 07 --stop 14
```

Generate the additional dissertation-quality figure set after the main analysis:

```powershell
python scripts\run_pipeline.py --figures-only
```

Each script can also be run separately from the repository root.

## Analysis sequence

| Script | Purpose |
| --- | --- |
| `00_download_stations.py` | Downloads NRW water-quality station metadata. |
| `02_profile_raw_water_quality.py` | Audits archive structure, fields and parameter labels. |
| `03_clean_water_quality.py` | Standardises records, units and qualifiers for the six indicators. |
| `13_audit_nrw_quality_flags.py` | Audits result qualifiers and quality-control exclusions. |
| `01_station_overview.py` | Summarises station types and spatial coverage. |
| `04_exploratory_analysis.py` | Produces initial six-indicator exploratory analysis. |
| `06_compare_all_vs_mine.py` | Compares all Welsh observations with the mine-related subset. |
| `07_mine_related_analysis.py` | Selects mine-related stations and analyses multi-metal relationships. |
| `08_pbzn_flow_analysis.py` | Retrieves NRFA data and performs automated Pb/Zn-flow matching. |
| `10_manual_flow_matching_validation.py` | Applies and evaluates manually reviewed flow-gauge matches. |
| `14_pbzn_censoring_sensitivity.py` | Tests reporting-limit treatment scenarios. |
| `15_flow_window_sensitivity.py` | Tests same-day, 3-day and 7-day flow windows. |
| `16_create_thesis_figures_tables.py` | Creates the first report figure and table set. |
| `29_complete_final_analysis.py` | Produces final station- and mine-system-level Pb/Zn results. |
| `17_other_metals_flow_extension.py` | Extends the final analysis to Cu/Zn and Pb/Cu. |
| `18_generate_introduction_schematics.py` | Generates the Introduction schematics. |
| `19_regenerate_figure_4_5_manual_validation.py` | Regenerates the final manual-matching validation figure. |
| `20_regenerate_figure_a_4_multi_metal_scatterplots.py` | Regenerates the final multi-metal appendix figure. |
| `21_build_dissertation_figure_pack.py` | Builds the complete publication-quality figure and table pack. |

The numbering preserves the order in which the analysis was developed, so some numbers are intentionally absent.

## Reproducibility notes

- Manual hydrological decisions and their supporting metadata are encoded in `10_manual_flow_matching_validation.py`, so the validation audit trail is versioned with the analysis.
- Below-reporting-limit records are retained with qualifiers. The final principal Pb/Zn analysis uses uncensored Pb-Zn pairs, while alternative treatments are evaluated as sensitivity scenarios.
- Flow percentiles describe the relative hydrological state at each matched NRFA gauge; they are not local instantaneous discharge measurements at the water-quality station.
- Generated values are not hard-coded into the principal analysis. Later scripts read the intermediate products made by earlier steps, so the analysis scripts should be run in the documented order.
- Do not use Git's force-add option for ignored data files. The repository is designed to publish code without redistributing source archives or derived site-level datasets.

## Data sources

- Natural Resources Wales, Water Quality Archive and monitoring-station metadata.
- UK Centre for Ecology & Hydrology, National River Flow Archive API: <https://nrfaapps.ceh.ac.uk/nrfa/nrfa-api.html>.
