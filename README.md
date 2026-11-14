# Harmonized Burning Activity Calendar — MODIS × VIIRS

NASA Space Apps Challenge 2026 · Brazil pilot

An interactive web application for exploring when burning activity occurs in a
selected region. It combines a monthly calendar, historical comparisons,
seasonality charts and downloadable data, with the goal of comparing satellite
records on a consistent VIIRS-equivalent scale.

**Status:** the application runs locally with a clearly labeled development
mock. The final harmonized dataset and scientific validation are pending from
the data team. Public deployment is on hold until the real data are available.
No public application URL is available yet.

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

- Select an area by drawing rectangles/polygons, or entering coordinates and radius.
- Apply illustrative 100 km examples for Pantanal, Matopiba and Acre.
- Explore a year-by-month calendar with accessible Viridis and PuOr color scales.
- View **Fire map**, a classified NASA FIRMS observation layer with fixed count
  ranges, a map legend, sensor/month controls, per-cell tooltips and a cell CSV.
- Compare the latest available month with earlier complete years.
- Inspect annual activity and monthly seasonality, with incomplete periods identified.
- Download the monthly regional CSV or export a PNG with the chart camera button.
- Review methodology, exploratory figures and validation metrics when supplied.

Drawings are drafts until **Apply map selection** is clicked. Coordinate filters
are applied with **Update**; their map preview is optional. Cell values can be
hidden for a clearer calendar on narrow screens.

## Run locally

Run all commands from the repository root. Development was tested with Python 3.13.

### Windows (PowerShell)

```powershell
py -3.13 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe app/make_mock.py
.venv/Scripts/python.exe -m streamlit run app/app.py
```

### Linux / macOS

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app/make_mock.py
.venv/bin/python -m streamlit run app/app.py
```

Open `http://localhost:8501`. The tracked `grid_monthly.parquet` is sufficient to
generate the development mock; downloading the raw archive is not necessary
for front-end development.

The mock generator uses MODIS × 3.8 before 2012 and VIIRS counts thereafter.
This provisional factor is **not validated harmonization**. The mock is local,
ignored by Git, and identified in the interface, chart titles and CSV exports.

The **Fire map** tab reads the separate, observed counts in the tracked monthly
grid (`n_modis` / `n_viirs`), not the calendar mock. Its fixed Viridis classes are
1–5, 6–20, 21–100, 101–500 and more than 500 detections per cell/month. These are
count ranges, not fire severity or burned-area classes. Its date controls are
independent of the calendar range. Raw MODIS and VIIRS counts are not directly
comparable, and final coverage/quality review remains pending. Unfilled cells
are unclassified, not proof of no fire. Publishing still waits for real harmonized data.

When `data/processed/harmonized.parquet` exists, the app prioritizes it over the
mock and checks its basic contract. An invalid real file is reported rather
than silently replaced by mock data. A valid file alone does not establish
scientific acceptance; the science team must confirm its calibration and validation.

## Data and planned scientific method

Source: [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/), including the
[historical archive](https://firms.modaps.eosdis.nasa.gov/download/).
The existing exploratory pipeline uses MODIS Collection 6.1 and VIIRS S-NPP
375 m country files for Brazil, 2001–2025. Extending the dataset to 2026 is a
separate data-team task.

The planned method in [specs/plan.md](specs/plan.md) calibrates Terra and Aqua
separately against S-NPP during 2012–2021, by 5° block and calendar month,
with a national-month fallback for groups with few MODIS detections. It converts
pre-2012 MODIS activity to the VIIRS scale, accounting for the Terra-only period,
and uses observed VIIRS activity from 2012 onward. Out-of-sample validation,
coverage flags and the final static-source mask remain the science team's work.
No accuracy targets are claimed as achieved by the current mock.

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

Participant names and the public app link will be finalized by the group before submission.
