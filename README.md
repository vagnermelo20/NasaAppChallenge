# Harmonized Burning Activity Calendar — MODIS × VIIRS

NASA Space Apps Challenge 2026 · Brazil pilot

**Live app:** https://ember-fire-calendar.streamlit.app

An interactive web application for exploring when burning activity occurs in a
selected region. It combines a monthly calendar, historical comparisons,
seasonality charts and downloadable data, with the goal of comparing satellite
records on a consistent VIIRS-equivalent scale.

**Status:** the application now uses the delivered real harmonized dataset:
1,252,185 cell-month records for 2001–2026 (2026 provisional; months with missing observation days flagged).
The map, calendar, trends and CSV exports are connected to this delivery.
Final-method validation is complete: the 0.25° cell peak-month criterion (80%) was not met
(73.7%; 90.4% within ±1 month); see the methodology for all scales.

## Why harmonization matters

MODIS and VIIRS detect active fire hotspots differently. A direct switch between
their raw counts can introduce a sensor-related discontinuity. The project aims
to preserve the historical MODIS record while providing continuity with VIIRS.

Hotspots are satellite detections, not unique fires or burned area. The app does
not forecast ignition or provide operational emergency alerts.

## Features

**EMBER** is built so that anyone can use it, with no satellite knowledge. It has two tabs:

- **Map** — NASA FIRMS hot spots of the latest 7 days on satellite imagery with place names. From far away
  they show as glowing orange/yellow areas; zoom in to a smaller area and every hot spot in view is loaded as a red dot. Choose the latest day, 7 days, 30 days, 12 months or any
  dates since 2001 (no limit). Click a dot to see which satellite saw it, when (Brasília time) and how strong its heat was compared with other hot spots. Draw a box or shape
  on the **same map** and press **Show fire history for this area** — or type a place (latitude, longitude and a distance in km). Right below the map, every hot spot inside the area on the chosen dates is listed in a table and can be downloaded as CSV (UTC time, FRP, harmonized weight). Everything below is for that area
  (or all of Brazil): plain sentences (fire season, worst month, when to get ready, worst year, last full month
  vs usual), a year × month fire calendar (optionally compared with a usual year), hot spots per day, week or
  month, a usual year, hot spots per year, "was the last month worse than usual?", a short "Why can we compare
  2005 with 2024?" demo, the uncertainty for years before 2012 and a CSV download.
- **How it works** — the project in seven simple steps.

Hot spots are satellite detections, not unique fires or burned area.

## Run locally

Run all commands from the repository root. Development was tested with Python 3.13.

### Windows (PowerShell)

```powershell
py -3.13 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m streamlit run app/app.py
```

### Linux / macOS

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app/app.py
```

Open `http://localhost:8501`. The real scientific files are tracked in the
repository, so no mock generation or raw-archive download is needed to run the app.
The optional `app/make_mock.py` remains available for development without the
real file; its output is ignored whenever the real harmonized file exists.

The mock generator uses MODIS × 3.8 before 2012 and VIIRS counts thereafter.
This provisional factor is **not validated harmonization**. The mock is local,
ignored by Git, and identified in the interface, chart titles and CSV exports.

When `data/processed/harmonized.parquet` exists, the app prioritizes it over the
mock and checks its basic contract. An invalid real file is reported rather
than silently replaced by mock data. A valid file alone does not establish
scientific acceptance; the science team must confirm its calibration and validation.

## Data and delivered scientific method

Source: [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/), including the
[historical archive](https://firms.modaps.eosdis.nasa.gov/download/).
The existing exploratory pipeline uses MODIS Collection 6.1 and VIIRS S-NPP
375 m country files for Brazil, 2001–2025, plus 2026 from the FIRMS API (standard data to 31 July,
near-real-time after; no S-NPP data since 2 November 2026).

The delivered method in [docs/metodologia.md](docs/metodologia.md) calibrates Terra and Aqua
separately against S-NPP during 2012–2021, by 5° block and calendar month,
with a national fallback and a 2° local refinement shrunk toward the block value.
It combines Terra and Aqua by inverse-variance weighting, accounting for the
Terra-only period, and uses processed S-NPP observations from 2012 onward.
The static-source mask and incomplete-month flags are included in the delivery.
Methodology highlights `prova_harmonizacao`, the final-method evidence, separately
from version-1 metrics. National correlation is reported as 0.998; these aggregate
results do not replace the pending final-method cell-scale peak-month criterion.

### Input contract

One row per 0.25° cell and UTC month:

| Field | Meaning |
|---|---|
| `lat`, `lon` | Southwest corner of the cell; its center is +0.125° in each axis |
| `ano`, `mes` | Year and month |
| `focos_harmonizados` | Nonnegative activity in VIIRS-equivalent hotspot units |
| `fonte` | `modis_convertido` or `viirs` |
| `dado_incompleto` | Incomplete observation period |

The app selects cells by their centers. Under the agreed sparse-data contract,
missing cell-month rows within dataset coverage are treated as zero. Entire
missing observation months need additional coverage metadata. A selection with
no dataset cell centers is identified explicitly and should be enlarged.

### Historical comparisons

Each complete target month is compared with the same month in earlier complete
years within the selected range. The target does not contribute to its own
baseline. Zero medians, missing history and incomplete target months produce no
percentage anomaly. Descriptive activity categories use historical percentiles
and require at least three reference years. They are not predictions.

CSV columns are `year`, `month`, `hotspots`, `anomaly_pct`, `incomplete`, `source`,
`dataset` and `region_wkt`. The calendar and CSV use the same anomaly calculation.

## Verification and handoff

```powershell
.venv/Scripts/python.exe -m unittest app.test_delivery -v
.venv/Scripts/python.exe -m app.check_release
```

The release check is read-only and exits with status 2 while required scientific
artifacts are missing or invalid. Passing it means artifacts are ready for review,
not that the scientific criteria or browser checks have been accepted.

See [app/VERIFY.md](app/VERIFY.md) for real-browser/mobile checks, integration with
Person A and deployment preparation. Leaflet drawing, PNG appearance and mobile
layout still require manual review. Public hosting will wait for real data.

## Repository layout

| Path | Purpose |
|---|---|
| `app/app.py` | Streamlit application |
| `app/make_mock.py` | Local development dataset generator |
| `app/test_delivery.py` | Data and UI regression tests |
| `app/check_release.py` | Read-only scientific-artifact readiness report |
| `notebooks/` | Data ingestion and exploratory scientific analysis |
| `data/processed/` | Monthly grid and delivered harmonized data |
| `reports/` | Exploratory figures and delivered validation metrics |
| `specs/` | Requirements, implementation plan and task tracking |

Raw data, the mock, virtual environments and credentials must remain untracked.
The original notebooks and figures are preserved for the scientific work and presentation.

## Team responsibilities

- **Person A — Data/science:** calibration, coverage, validation and final scientific artifacts.
- **Person B — Application:** regional queries, visualization, accessibility and exports.
- **Joint delivery:** deployment, final credits, presentation, video and Space Apps submission.

Public app: https://ember-fire-calendar.streamlit.app · Participant names will be finalized by the group before submission.
