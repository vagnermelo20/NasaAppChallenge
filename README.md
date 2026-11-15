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
(73.7%; 90.4% within ±1 month); see the methodology for all scales. Data for 2026 and public
deployment are still pending. No public application URL is recorded yet.

## Why harmonization matters

MODIS and VIIRS detect active fire hotspots differently. A direct switch between
their raw counts can introduce a sensor-related discontinuity. The project aims
to preserve the historical MODIS record while providing continuity with VIIRS.

Hotspots are satellite detections, not unique fires or burned area. The app does
not forecast ignition or provide operational emergency alerts.

## Features

The interface is branded **EMBER · Earth Fire Observatory**. It opens on a
map-focused workspace with a dark observation catalog, compact indicators,
layer opacity controls, a source card and a matching map legend. Calendar,
Trends and Methodology load their content only when selected.

The map opens in **Hotspot locations** on Esri satellite imagery. Small red dots
show actual detection coordinates from the science team's annual point files,
without halos or proportional sizing. Dots are detections, not unique fires.
The indicators and cell export retain the monthly analysis totals. **Analysis grid**
retains the original polygons. The compact horizontal legend, region outline
and fullscreen control keep the map readable. Dark atlas and the street
map are alternative backgrounds, with provider attribution. Esri background
imagery is context and is not synchronized to the NASA observation date.

- Select an area by drawing rectangles/polygons, or entering coordinates and radius.
- In Calendar, expand **Pre-2012 uncertainty · 2° monthly regions** to inspect
  the delivered nominal 90% calibration band for a full 2° region-month.
  Bounds use the science team's MODIS-count factors; they are not added across
  regions/months or applied to exact-day searches. A dedicated CSV records the
  region, estimate, factors and bounds. This delivery awaits Person A's review.
- **Hotspot search:** query an inclusive UTC date interval (up to 92 days),
  filter by sensor/applied calendar area, inspect detections and export a CSV
  (date, time UTC, coordinates, satellite, FRP in MW and harmonized weight).
  Queries above 200,000 detections require a narrower selection; no partial CSV
  is offered. Compare the same dates in up to six start years using summed
  harmonized weights. Before 2012 these exact-day comparisons are approximate;
  the monthly calibration uncertainty is not an exact-day confidence interval.
  Incomplete intervals are excluded from numerical comparisons; February 29
  is never silently moved in non-leap years. The archive follows MODIS before
  2012 and S-NPP afterward, rather than retaining every sensor in every year.
- Apply illustrative 100 km examples for Pantanal, Matopiba and Acre.
- Explore a year-by-month calendar with accessible Viridis and PuOr color scales.
- View **Fire map** using real harmonized activity or processed sensor observations,
  with fixed color ranges, a map legend, period controls, tooltips and cell CSV.
- Compare the latest available month with earlier complete years.
- Inspect annual activity and monthly seasonality, with incomplete periods identified.
- Download the monthly regional CSV or export a PNG with the chart camera button.
- Review the delivered methodology, final-method evidence and versioned validation metrics.

Drawings are drafts until **Apply map selection** is clicked. Coordinate filters
are applied with **Update**; their map preview is optional. Cell values can be
hidden for a clearer calendar on narrow screens.

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

The **Fire map** opens on `harmonized.parquet`, the same series used by Calendar
and Trends. It preserves fractional converted values and warns about incomplete
months. The alternative **Sensor observations** product aggregates `n` by
satellite/day-night from `grid_sat.parquet`, using the science team's preprocessing.
VIIRS observations and the post-2012 harmonized series therefore agree for the
same cells and month. The legacy grid is used only if the new satellite grid is
absent, with an explicit warning.

Fixed Viridis ranges are >0–5, >5–20, >20–100, >100–500 and more than 500 activity
units per cell/month. The legend identifies observed detections versus
VIIRS-equivalent units. These are not severity or burned-area classes. Map dates
are independent of calendar years; sensor-specific MODIS and VIIRS counts are
not directly comparable. Unfilled cells are unclassified, not proof of no fire.

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
